# -*- coding: utf-8 -*-
from odoo import models, api, tools, exceptions, _
from dateutil.relativedelta import relativedelta
from .. import enable_banking_tools as eb
from datetime import datetime
import requests
import logging
import os.path
import uuid
import pytz
import json
import time
import jwt


_logger = logging.getLogger(__name__)


class EnableBankingAPIBase(models.Model):
    _name = 'enable.banking.api.base'
    _description = '''Abstract model that contains core methods that 
    are used to connect and interact with Enable Banking API'''

    # Auth methods ----------------------------------------------------------------------------------------------------

    @api.model
    def get_api_jwt_auth(self):
        """
        Method that is used to generate JSON web token signature
        with the Enable Banking private key. JWT signature is used
        to authenticate every API call.
        :return: JWT auth value (str)
        """
        param_obj = self.sudo().env['ir.config_parameter']
        configuration = self.get_configuration(fully_functional=False)

        # Get the needed config parameters
        tl_api_url = param_obj.get_param('enable_banking_tl_api_url')
        main_url = param_obj.get_param('enable_banking_main_url')
        key_path = param_obj.get_param('enable_banking_private_key_path')
        # Check base constraints
        if not main_url or not tl_api_url:
            raise exceptions.ValidationError(_('Enable banking URLs are not defined'))
        if not key_path:
            raise exceptions.ValidationError(_('Enable banking private key path is not specified'))
        if not os.path.isfile(key_path):
            raise exceptions.ValidationError(_('Enable banking private key does not exist'))

        # Create message headers
        message_headers = {
            'typ': 'JWT',
            'alg': 'RS256',
            'kid': configuration.application_key,
        }
        # Create message body, generate token start and expire times
        token_iat = int(datetime.utcnow().strftime('%s'))
        message_body = {
            'iss': main_url,
            'aud': tl_api_url,
            'iat': token_iat,
            'exp': token_iat + 3600,
        }
        # Read private key
        with open(key_path, 'rb') as key_data:
            private_key = key_data.read()

        # JWT Encode and return the authorization string
        auth_string = jwt.encode(
            message_body, private_key,
            algorithm='RS256', headers=message_headers
        )
        return auth_string

    # Session API methods ---------------------------------------------------------------------------------------------

    @api.multi
    def api_initiate_user_session(self, connector, session_code):
        """
        Method that is used to authorise access to specific
        bank connector. Session code that is received after
        redirection must be passed to the method, and it is used
        to get a permanent session ID.
        :return: None
        """
        # Configuration is checked before each API method
        if not self.get_configuration(fully_functional=False):
            return

        request_content = {'code': session_code}
        # Call the endpoint
        successful_call, response_data = self.call(
            action='post_init_session',
            extra_data={'request_content': request_content},
            connector=connector,
        )
        # Current date + max time to live - 1 day (earlier inform message)
        session_valid_to = datetime.utcnow() + relativedelta(
            seconds=eb.MAX_TOKEN_TTL_SECONDS) - relativedelta(days=1)

        accounts = response_data.get('accounts')
        if successful_call and accounts:
            connector.write({
                'session_id': response_data['session_id'],
                'valid_to': session_valid_to,
                'api_state': 'working',
            })
            # Create banking accounts
            connector.create_banking_accounts(accounts_data=accounts)
        else:
            if accounts:
                user_message = system_message = _('Failed to fetch external accounts, contact administrators')
            else:
                message_base = _('Failed to authenticate the session: {}')
                system_message = message_base.format(response_data['system_notification'])
                user_message = message_base.format(response_data['status_description'])

            # If it fails, post two messages for admin and user
            connector.message_post(body=system_message)
            connector.write({
                'api_state': 'failed',
                'last_api_error_message': user_message,
            })

    @api.model
    def api_terminate_user_session(self, connector):
        """
        Method that is used to terminate  the
        session to specific bank connector.
        :return: None
        """
        # Configuration is checked before each API method
        if not self.get_configuration():
            return

        successful_call, response_data = self.call(
            action='terminate_session',
            extra_data={'object_id': connector.session_id},
            connector=connector,
        )
        if successful_call:
            # Reset connector values on successful call
            connector.reset_connectors_sessions()
        else:
            # If it fails, post two messages for admin and user
            message_base = _('Failed to terminate the session: {}')
            connector.message_post(
                body=message_base.format(response_data['system_notification']))
            connector.write({
                'last_api_error_message': message_base.format(response_data['status_description']),
            })

    @api.model
    def api_authorize_bank_connector(self, connector):
        """
        Method that is used to authorise access to specific
        bank connector. Endpoint returns URL that is displayed
        to the user, authentication takes place in external system.
        :return: API response data (dict)
        """
        # Configuration is checked before each API method
        # those that return data, have raises
        base_url = self.sudo().env['ir.config_parameter'].get_param('enable_banking_redirect_url')
        if not self.get_configuration(fully_functional=False) or not base_url:
            raise exceptions.ValidationError(
                _('Enable banking settings are not configured. Contact administrators')
            )

        # Maximum allowed validity period
        valid_unit = (datetime.now(pytz.utc) + relativedelta(seconds=eb.MAX_TOKEN_TTL_SECONDS)).isoformat()
        # Generate random initialization vector and write it to connector
        state_init_vector = '{}__{}__{}'.format(self.env.cr.dbname, str(uuid.uuid1()), connector.id)
        connector.write({'latest_state_vector': state_init_vector})
        # Compose redirect_url URL
        redirect_url = '%s/e_banking_auth' % base_url
        # Build request content
        request_content = {
            'access': {'valid_until': valid_unit, },
            'aspsp': {
                'name': connector.name,
                'country': connector.country_id.code,
            },
            'state': state_init_vector,
            'redirect_url': redirect_url,
            'psu_type': connector.psu_type,
        }
        # Call the endpoint
        successful_call, response_data = self.call(
            action='post_authenticate',
            extra_data={'request_content': request_content},
            connector=connector,
        )
        # On successful call, parse the authorization url and write it to connector
        if not successful_call:
            self.api_error_message_handler(response_data=response_data, data_type='Session authentication')
        return response_data

    # Account API methods ---------------------------------------------------------------------------------------------

    @api.model
    def api_get_accounts_balances(self, e_banking_accounts=None):
        """
        Method that is used to fetch end balances for connector
        enable banking accounts. Method can be called on single/multi
        accounts, or single multi/connectors.
        :param e_banking_accounts: Optional, forced enable.banking.account (records/None)
        :return: None
        """
        # Configuration is checked before each API method
        if not self.get_configuration():
            return

        if e_banking_accounts is None:
            # Get all of the activated banking accounts
            e_banking_accounts = self.env['enable.banking.connector'].get_configured_accounts()
        # Loop and call balance fetching endpoint
        for account in e_banking_accounts:
            self.api_get_account_balance(account)
            # Commit after each account
            self.env.cr.commit()

    @api.model
    def api_get_account_balance(self, e_banking_account):
        """
        Method that is used to fetch end balance for specific banking account
        :param e_banking_account: Enable banking account (record)
        :return: successful_call (bool)
        """
        # Configuration is checked before each API method
        if not self.get_configuration():
            return

        successful_call, response_data = self.call(
            action='get_account_balance',
            extra_data={'object_id': e_banking_account.external_id},
            connector=e_banking_account.bank_connector_id,
        )
        if successful_call:
            # Convert fetched data to list
            fetched_balances = list(response_data['balances'])
            # Check fetched balance types and determine the one to use
            balance_mapping = {balance['balance_type']: balance for balance in fetched_balances}

            # Default balance type is INTERIM
            balance_type = eb.INTERIM_BALANCE
            if eb.ACCOUNTING_BALANCE in balance_mapping:
                balance_type = eb.ACCOUNTING_BALANCE
            elif eb.INTERIM_BOOKED_BALANCE in balance_mapping:
                balance_type = eb.INTERIM_BOOKED_BALANCE

            # Get the data, if INTERIM balance is not supplied, skip update altogether
            balance_to_use = balance_mapping.get(balance_type)

            # Loop through fetched balance data
            if balance_to_use:
                # Parse the balance amount and update the account
                try:
                    balance_amount = float(balance_to_use['balance_amount']['amount'])
                except (ValueError, TypeError):
                    balance_amount = 0.0
                e_banking_account.write({
                    'api_end_balance': balance_amount,
                    'api_balance_update_date': datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                })
        else:
            self.api_error_message_handler(
                response_data=response_data, data_type='Balance fetching',
                e_banking_account=e_banking_account,
            )
        return successful_call

    @api.model
    def api_get_bank_transactions(self, journal=None, date_from=None, date_to=None):
        """
        Method that is used to authorise access to specific
        bank connector. Endpoint returns URL that is displayed
        to the user, authentication takes place in external system.
        :return: API response data (dict)
        """
        def convert_dates(date_str):
            """Convert date string to datetime object"""
            try:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
            return date_dt

        # Configuration is checked before each API method
        if not self.get_configuration():
            return

        # Convert dates to datetime objects and then convert them to ISO-format
        date_from = (
            convert_dates(date_from) if date_from else datetime.now() - relativedelta(days=1)
        ).date().isoformat()

        # Get either all of the e_banking_accounts or only ones related to the journal
        if journal is None:
            e_banking_accounts = self.env['enable.banking.connector'].get_configured_accounts()
        else:
            # Constraint checks for account are done beforehand
            e_banking_accounts = self.env['enable.banking.account'].search(
                [('journal_id', '=', journal.id)]
            )
        base_request_content = {'date_from': date_from, 'transaction_status': 'BOOK'}
        # Append date to to the request base only if it exists
        # banks default to current day and operate faster without this param.
        if date_to:
            date_to = convert_dates(date_to).date().isoformat()
            base_request_content['date_to'] = date_to
        # Loop and call balance fetching endpoint
        for account in e_banking_accounts:
            total_transactions = []
            continuation_key = None
            # Measure while True loop time, so it does not get stuck
            start_time = time.time()
            # While True is handled with a timer just in case.. Otherwise it breaks if
            # no continuation key is passed to the transaction response message
            while True:
                # Update the query with transaction continuation key if it's present
                if continuation_key:
                    request_content = base_request_content.copy()
                    request_content['continuation_key'] = continuation_key
                else:
                    request_content = base_request_content
                # Call the endpoint
                successful_call, response_data = self.call(
                    action='get_account_transactions',
                    extra_data={'object_id': account.external_id, 'request_content': request_content},
                    connector=account.bank_connector_id,
                )
                if successful_call:
                    # Update total transaction list and check for continuation key
                    total_transactions.extend(list(response_data['transactions']))
                    continuation_key = response_data['continuation_key']
                    # If there's no continuation key, all of the transactions have been fetched
                    if not continuation_key:
                        break
                else:
                    self.api_error_message_handler(
                        response_data=response_data, data_type='Balance fetching', e_banking_account=account,
                    )
                    break
                # Check the elapsed time and break the loop if its more than MAX_TRANSACTION_FETCHING_TTL
                elapsed_time = time.time() - start_time
                if elapsed_time > eb.MAX_TRANSACTION_FETCHING_TTL:
                    _logger.info('EBanking [{}]-[{}]: Not waiting for transactions after {} seconds....'.format(
                        account.bank_connector_id.display_name, account.account_iban,
                        eb.MAX_TRANSACTION_FETCHING_TTL)
                    )
                    break
            # Process fetched transactions for current account
            if total_transactions:
                self.with_context(batch_fetch_date_to=date_to).process_transactions(total_transactions, account)
            # Commit after each account
            self.env.cr.commit()

    # Misc API methods ------------------------------------------------------------------------------------------------

    @api.multi
    def api_get_bank_list(self):
        """
        Method that is used to fetch available bank
        connectors based on the application ID.
        Used when integration is first initiated
        :return: API response data (dict)
        """
        # Configuration is checked before each API method
        # those that return data, have raises
        if not self.get_configuration(fully_functional=False):
            raise exceptions.ValidationError(
                _('Enable banking settings are not configured. Contact administrators')
            )

        # Call the endpoint to get the bank data
        successful_call, response_data = self.call(
            action='get_bank_list',
            extra_data={},
        )
        if not successful_call:
            self.api_error_message_handler(response_data=response_data, data_type='Bank list')
        return response_data

    # API core block --------------------------------------------------------------------------------------------------

    @api.model
    def call(self, action, extra_data=None, connector=None):
        """
        Main method used to prepare data/structures for Enable Banking API call.
        :return: True/False (based on success of the call), response_data
        """
        # Get the required data and call the endpoint
        api_data = self.get_api_endpoint_data(action, extra_data=extra_data)
        response = self.call_api_endpoint(api_data)

        # Sanitize the response, parse the data and status code
        response_data, status_code = self.sanitize_api_response(response, connector)

        # Check whether call was successful
        successful_call = status_code == 200
        return successful_call, response_data

    @api.model
    def call_api_endpoint(self, api_data):
        """
        API core method that aggregates the data and calls specific Enable banking API endpoint.
        Each call is authenticated by using JWT in request headers.
        :param api_data: {request_endpoint, request_method, request_url, data, data_type} (dict)
        :return: response of specific API endpoint (object)
        """
        req_method = api_data['request_method']
        request_url = api_data['request_url']
        request_content = api_data['data'].get('request_content')
        # Get JWT authentication string
        auth_string = self.get_api_jwt_auth()
        # Base header data that is the same for POST/GET
        base_headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(auth_string),
        }
        try:
            # Initiate the request based on the method
            if req_method == 'GET':
                # Prepare GET request parameter string
                request_str = str()
                if request_content:
                    request_str = '&'.join('%s=%s' % (k, v) for k, v in request_content.items())
                response = requests.get(request_url, headers=base_headers, params=request_str)
            elif req_method == 'DELETE':
                response = requests.delete(request_url, headers=base_headers)
            else:
                # JSON dump request content if it exists
                json_data = None
                if request_content:
                    json_data = json.dumps(request_content)
                response = requests.post(request_url, headers=base_headers, data=json_data)
        except Exception as e:
            _logger.info('Enable Banking API REQUEST ERROR: {}'.format(e.args[0]))
            raise exceptions.ValidationError(
                _('Could not reach Enable Banking server. Please contact administrators')
            )
        return response

    @api.model
    def get_api_endpoint_data(self, action, extra_data=None):
        """
        Prepare specific Enable Banking API endpoint data based on passed action value
        :param action: API action that is mapped to specific endpoint (str)
        :param extra_data: extra parameters that are passed to the endpoint (dict/None)
        :return: prepared data (dict)
        """

        extra_data = {} if extra_data is None else extra_data
        # Enable Banking endpoint url that is  mapped to action in our system
        endpoint_mapping = {
            'post_authenticate': '/auth',
            'post_init_session': '/sessions',
            'get_bank_list': '/aspsps',
            'get_account_balance': '/accounts/{object_id}/balances',
            'get_account_transactions': '/accounts/{object_id}/transactions',
            'terminate_session': '/sessions/{object_id}',
        }
        # Enable Banking method (GET, POST, DELETE) based on action in our system
        method_mapping = {
            'post_authenticate': 'POST',
            'post_init_session': 'POST',
            'get_bank_list': 'GET',
            'get_account_balance': 'GET',
            'get_account_transactions': 'GET',
            'terminate_session': 'DELETE',
        }
        # Gets method, endpoint, and other info based on the action
        endpoint = endpoint_mapping.get(action)
        method = method_mapping.get(action)
        # If not method or endpoint exists, raise an exception
        if not endpoint or not method:
            raise exceptions.ValidationError(_('Incorrect endpoint is passed!'))
        # Format the endpoint
        endpoint = endpoint.format(**extra_data)
        base_url = self.sudo().env['ir.config_parameter'].get_param('enable_banking_tl_api_url')
        if not base_url:
            raise exceptions.ValidationError(_('Enable banking URLs are not defined'))
        # Format the full URL
        req_url = 'https://{}{}'.format(base_url, endpoint)
        return {
            'request_url': req_url,
            'request_endpoint': endpoint,
            'request_method': method,
            'data': extra_data,
        }

    @api.model
    def sanitize_api_response(self, response, connector=None):
        """
        Sanitize the response of specific Enable Banking API endpoint
        :param response: response (object)
        :param connector: Enable banking connector record
        :return: response content (dict), status code (int)
        """
        # Parse the JSON and get status code
        try:
            response_content = response.json()
            status_code = response.status_code
        except (ValueError, AttributeError):
            response_content = {}
            status_code = 500
        # Prepare error description strings
        error_str = description = str()
        # If status code is not 200, raise an error (or send a bug)
        if status_code != 200:
            # Get both of the error descriptions
            ext_e_code = response_content.get('error')
            description = response_content.get('message')
            # Fetch description from mapping based on status code if it does not exist
            if not description:
                description = eb.GENERAL_API_RESPONSE_MAPPING.get(status_code, _('Unexpected error'))
            # Compose an error message
            error_str = _('Enable banking API error: {}\nDescription: {}\nStatus code - [{}]').format(
                ext_e_code, description, status_code)
            _logger.info(error_str)

            # Set some extra flags based on the received data
            if status_code in eb.EXTERNAL_FAILURE_CODES or ext_e_code in eb.EXTERNAL_FAILURE_RESPONSES:
                response_content['external_failure'] = True

            if connector and ext_e_code in [eb.AUTHORIZATION_FAILURE, eb.EXPIRED_SESSION]:
                response_content['authorization_failure'] = True
                if not connector.authorization_failure:
                    # Rollback, write authorization failure and raise the exception on the first run
                    self.env.cr.rollback()
                    connector.authorization_failure = True
                    self.env.cr.commit()
                    raise exceptions.ValidationError(error_str)

        # If we receive 200 status code and connector is not None,
        # and is set as auth failure - reset the value.
        elif status_code == 200 and connector and connector.authorization_failure:
            # Add extra logging to determine auth failure reset responses
            _logger.info('EnableBanking: Auth failure re-set, received data - %s' % str(response_content))
            connector.authorization_failure = False
        # Always attach detailed admin error to the response
        response_content.update({
            'system_notification': error_str,
            'status_description': description,
            'status_code': status_code,
        })
        return response_content, status_code

    # Processing methods ----------------------------------------------------------------------------------------------

    @api.model
    def process_transactions(self, transactions, e_banking_account):
        """
        Method used to process transactions that were received by an API response.
        Transactions are grouped by a date to a format that corresponds
        to account.bank.statement.line structure. Grouped transactions
        are passed to bank statement creation method.
        :param transactions: list of transaction dicts received via API (list)
        :param e_banking_account: enable.banking.account record that transactions belong to (record)
        :return: None
        """
        earliest_date = datetime.now()
        transactions_by_date = {}
        journal = e_banking_account.journal_id
        for transaction in transactions:
            if transaction['status'] != 'BOOK':
                continue
            # Get transaction entry reference
            entry_reference = transaction.get('entry_reference')
            if not entry_reference:
                continue
            # Take latest out of three dates, and skip if it does not exist
            tr_date = max(transaction['booking_date'], transaction['value_date'], transaction['transaction_date'])
            if not tr_date:
                continue
            # Set earliest batch date
            tr_date_dt = datetime.strptime(tr_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if tr_date_dt < earliest_date:
                earliest_date = tr_date_dt

            # Check if transaction is outbound
            outbound = transaction.get('credit_debit_indicator', 'DBIT') == 'DBIT'

            # Get the amount which is represented in string format and convert amount based on a direction
            tr_amount = float(transaction['transaction_amount'].get('amount', '0.0'))
            tr_amount *= -1 if outbound else 1

            # Check whether the line already exists in the system using date, amount and IDs
            duplicate_line = self.env['account.bank.statement.line'].search(
                [('entry_reference', '=', entry_reference),
                 ('statement_id.sepa_imported', '=', True),
                 ('journal_id', '=', journal.id),
                 ('date', '=', tr_date)]
            )
            # Use filtered with float_compare for correct results
            if duplicate_line.filtered(lambda x: not tools.float_compare(x.amount, tr_amount, precision_digits=2)):
                continue
            # Set default date
            transactions_by_date.setdefault(tr_date, [])
            # Name and transaction reference
            tr_ref = transaction.get('reference_number')
            tr_name = str()
            remittance_information = transaction.get('remittance_information', [])
            if remittance_information and isinstance(remittance_information, list):
                # Sometimes it's not not filled with two values
                tr_name = remittance_information[1] if len(remittance_information) > 1 else remittance_information[0]

            # Get other party info from transaction
            partner_node = 'creditor' if outbound else 'debtor'
            # Get main partner nodes
            partner_block = transaction.get(partner_node, {}) or {}
            partner_account_block = transaction.get('{}_account'.format(partner_node), {}) or {}
            # Gather the info from the node
            partner_name = partner_block.get('name', str())
            partner_iban = partner_account_block.get('iban', str())

            partner_code = partner_id = None
            # Search for partner identification fields
            partner_code_block = partner_block.get('organisation_id', {}) or {}
            if not partner_code_block:
                partner_code_block = partner_block.get('private_id', {}) or {}

            if partner_code_block:
                # Get code value and code type
                partner_code = partner_code_block.get('identification')
                code_type = partner_code_block.get('scheme_name')
                code_searchable = None
                # Custom code type is always sanitized
                if code_type == 'CUST':
                    try:
                        # Only if len is lower than 10 and value can be
                        # converted to integer we recognize the value as valid
                        if len(partner_code) < 10:
                            partner_code = int(partner_code)
                            code_searchable = 'id'
                    except ValueError:
                        pass
                else:
                    # Get code searchable value
                    code_searchable = eb.BANK_PARTNER_CODE_TYPE_MAPPER.get(code_type)
                # Search for partner ID
                if code_searchable and partner_code:
                    partner_id = self.env['account.sepa.import'].get_partner_id(
                        partner_name=partner_name,
                        partner_iban=partner_iban,
                        partner_identification=(code_searchable, partner_code)
                    )
            # Prepare transaction values
            values = {
                'journal_id': journal.id,
                'amount': tr_amount,
                'name': tr_name or '/',
                'ref': tr_ref or '/',
                'date': tr_date,
                'entry_reference': entry_reference,
                'info_type': 'unstructured',
                'imported_partner_name': partner_name,
                'imported_partner_iban': partner_iban,
                'imported_partner_code': partner_code,
                'partner_id': partner_id,
            }
            transactions_by_date[tr_date].append(values)
        # After transactions are grouped, call bank statement creation
        if transactions_by_date:
            self.create_bank_statements(e_banking_account, transactions_by_date, earliest_date)

    @api.model
    def create_bank_statements(self, e_banking_account, transactions_by_date, earliest_date):
        """
        Method that creates account.bank.statement records from passed bulk
        of grouped and processed transactions that were received via API.
        Earliest date is used to fetch the end balance from the statement before
        this day (used as starting balance for statements-to-be created)
        :param e_banking_account: enable banking account record for which the statements are fetched (record)
        :param transactions_by_date: {'2020-01-01': [{TR1_DATA}, {TR2_DATA}]...} (dict)
        :param earliest_date: earliest date of the transaction bulk (object)
        :return: None
        """
        statements = self.env['account.bank.statement']
        journal = e_banking_account.journal_id

        base_domain = [
            ('journal_id', '=', journal.id),
            ('sepa_imported', '=', True),
            ('partial_statement', '=', False),
        ]
        # Check whether there is a statement day earlier than earliest date of this bulk
        # if it does exist, use it's end balance for further calculations
        before_batch_statement = self.env['account.bank.statement'].search(
            base_domain + [('date', '<', earliest_date)], limit=1, order='date desc, create_date desc')

        # If latest statement exits, and it's not a partial statement, we take it's end balance
        balance_end_compute = 0.0
        if before_batch_statement:
            balance_end_compute = before_batch_statement.balance_end_real

        # Loop through the list of dates, and check whether new statement should be created
        # or already existing statement should be updated with newly fetched lines
        sorted_transactions = sorted(transactions_by_date.items(), key=lambda k: k[0])
        for date, transactions in sorted_transactions:
            balance_start_compute = balance_end_compute
            amount_imported = 0.0
            lines = []
            # Loop through transactions, calculate imported amount and
            # add them to lines list of bank statement
            for tr in transactions:
                amount_imported += tr.get('amount')
                lines += [(0, 0, tr)]
            # Check whether the statement for current day exists
            statement = self.env['account.bank.statement'].search(
                base_domain + [('date', '=', date)], limit=1)

            # We cannot modify SEPA statement lines with PSD2 statement
            # thus if entry is already there, we just skip. Artificial statements are updated
            # as psd2 statements afterwards.
            if statement.line_ids and not statement.psd2_statement and not statement.artificial_statement:
                continue

            balance_end_compute = balance_start_compute + amount_imported
            # Create statement if it does not exist
            if not statement:
                statement_vals = {
                    'name': '/',
                    'date': date,
                    'journal_id': journal.id,
                    'balance_start': balance_start_compute,
                    'balance_end_factual': balance_end_compute,
                    'balance_end_real': balance_end_compute,
                    'sepa_imported': True,
                    'line_ids': lines,
                    'psd2_statement': True,
                }
                statement = self.env['account.bank.statement'].create(statement_vals)
            else:
                end_balance = statement.balance_end_real + amount_imported
                statement.write({
                    'line_ids': lines,
                    'state': 'open',
                    'balance_end_real': end_balance,
                    'balance_end_factual': end_balance,
                    'artificial_statement': False,
                    'psd2_statement': True,
                })
            statements |= statement

        # Try to normalize the statements in ascending way, if it fails (no initial starting entry),
        # execute the current day's balance fetching and normalize them in descending way
        normalized_ascending = self.env['account.bank.statement'].normalize_balances_ascending(journal_ids=journal.ids)
        if not normalized_ascending:
            # Update the end balances of all journals, and force the end balance to the latest statement
            # Because in this API we do not get the balance for specific date on statement call
            date_today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            # Search for today's statement
            today_statement = self.env['account.bank.statement'].search(
                [('sepa_imported', '=', True),
                 ('partial_statement', '=', False),
                 ('journal_id', '=', journal.id),
                 ('date', '=', date_today)],
                order='date desc, create_date desc', limit=1
            )
            # Check if batch date to is passed in the context, and if batch date to
            # is further than/equals to today, we can create today_statement and update
            # it's balance, since that implies that no transactions are missed
            date_to = self._context.get('batch_fetch_date_to')
            if not today_statement and (date_to and date_to >= date_today or not date_to):
                today_statement = self.env['account.bank.statement'].create({
                    'name': '/',
                    'date': date_today,
                    'journal_id': journal.id,
                    'sepa_imported': True,
                })
                today_statement.button_confirm_bank()

            # If today's statement exist, we fetch the realtime balance and update it
            if today_statement:
                # Call the endpoint and update the journal
                successful_call = self.with_context(
                    ignore_external_failures=True).api_get_account_balance(e_banking_account)
                if successful_call:
                    # If wall was successful, force the balances to current statement
                    balance = e_banking_account.api_end_balance
                    today_statement.write({'balance_end_real': balance, 'balance_end_factual': balance})

            # Normalize balances of bank statements descending
            empty_statements = self.env['account.bank.statement'].normalize_balances_descending(journal_ids=journal.ids)
            statements |= empty_statements

        # Check whether lines should be reconciled with GPM lines
        lines_to_skip = self.env['account.bank.statement.line']
        if not self.env.context.get('skip_autoreconciliation_sodra_gpm'):
            lines_to_skip = statements._auto_reconcile_SODRA_and_GPM()

        # Try to apply import rules and auto reconcile the lines with other accounting entries
        lines_to_skip += statements.with_context(skip_error_on_import_rule=True).apply_journal_import_rules()
        statements.mapped('line_ids').auto_reconcile_with_accounting_entries(lines_to_skip=lines_to_skip)

    # Other methods ---------------------------------------------------------------------------------------------------

    @api.model
    def get_configuration(self, fully_functional=True):
        """Return Enable banking configuration record after validation"""
        conf_obj = self.env['enable.banking.configuration']
        # Only return the configuration if it's configured
        configuration = conf_obj.search([])
        if configuration:
            # Check whether configuration should be fully functional or not
            working = configuration.application_key
            if fully_functional:
                working = working and configuration.api_state != 'not_initiated'
            if working:
                conf_obj = configuration
        return conf_obj

    @api.model
    def api_error_message_handler(self, response_data, data_type, e_banking_account=None):
        """
        Handles API error messages - logs the error, and conditionally raises
        :param response_data: API response data (dict)
        :param data_type: Data type of the API call (str)
        :param e_banking_account: eBanking account (record)
        :return: None
        """

        # If banking account is passed, compose identifier string
        identifier_string = 'API'
        if e_banking_account:
            identifier_string = '[{}]-[{}]'.format(
                e_banking_account.bank_connector_id.display_name,
                e_banking_account.account_iban,
            )

        # Check whether external failures should be ignored
        ignore_external_failures = self._context.get('ignore_external_failures')

        # Format the code with the description
        api_response_error = '[{}] / {}'.format(
            response_data['status_code'], response_data['status_description']
        )
        formatted_error_message = _('Enable Banking {}: {} error: {}').format(
            identifier_string, data_type, api_response_error,
        )
        # Log the info
        _logger.info(formatted_error_message)
        # Check whether there's any external failures (General, auth..)
        external_failures = response_data.get('authorization_failure') or response_data.get('external_failure')

        # If parsed data does not signify general external/auth failure and flag does not ignore them, raise
        if not ignore_external_failures or not external_failures:
            raise exceptions.ValidationError(formatted_error_message)

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_fetch_account_balances(self):
        """
        Cron that fetches current balance
        for all of the Enable banking accounts
        :return: None
        """
        self.with_context(ignore_external_failures=True).api_get_accounts_balances()

    @api.model
    def fetch_statements_daily(self):
        """
        Pseudo-cron (Called by another cron-job, but not by an actual cron record)
        that fetches daily bank statements for all of the Enable banking accounts
        :return: None
        """
        self.with_context(ignore_external_failures=True).api_get_bank_transactions()

    @api.model
    def fetch_statements_weekly(self):
        """
        Pseudo-cron (Called by another cron-job, but not by an actual cron record)
        that fetches weekly bank statements for all of the Enable banking accounts
        :return: None
        """
        date_from = (datetime.now() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.with_context(ignore_external_failures=True).api_get_bank_transactions(date_from=date_from)
