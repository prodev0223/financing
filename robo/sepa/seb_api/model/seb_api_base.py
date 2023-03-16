# -*- encoding: utf-8 -*-
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo import models, _, api, exceptions, tools
from dateutil.relativedelta import relativedelta
from ... import api_bank_integrations as abi
from .. import seb_api_tools as sb
from lxml import etree, objectify
from odoo.api import Environment
from datetime import datetime
import threading
import hashlib
import requests
import logging
import base64
import pytz
import json
import odoo
import os

_logger = logging.getLogger(__name__)


def convert_date(date_str):
    """Converts date-time string to date string"""
    try:
        date_str = (datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
    except ValueError:
        # If it excepts on ValueError, it means date is already w/o time
        pass
    return date_str


class SebAPIBase(models.AbstractModel):
    _name = 'seb.api.base'
    _description = 'Abstract model that holds SEB API base methods'

    # -----------------------------------------------------------------------------------------------------------------
    # API actions -----------------------------------------------------------------------------------------------------

    @api.model
    def api_fetch_end_balances(self, manual_action=False):
        """
        Method that is used to fetch balances for each SEB journal.
        :param manual_action: Identifies whether the action is manual or not
        :return: None
        """
        # Check whether API is correctly configured
        configuration = self.get_configuration(raise_exception=False)
        if not configuration.check_configuration() or not configuration.intra_day_endpoint:
            return

        # Get all SEB journals, loop through them and call the endpoint
        acc_journals = configuration.get_related_journals()
        for journal in acc_journals:
            # Validate the IBAN
            j_iban = journal.bank_acc_number
            try:
                validate_iban(j_iban)
            except exceptions.ValidationError:
                raise exceptions.UserError(_('SEB API: Incorrect IBAN number - {}!').format(j_iban))

            # Call the endpoint
            successful_call, response_data = self.call(
                action='get_balance',
                extra_data={'object_id': j_iban, 'manual_action': manual_action},
            )
            # If call is successful, self.parse the file and update the balances
            # otherwise raise an error
            if successful_call:
                xml_stream = response_data.get('xml_stream', str())
                grouped_data = self.process_balance_response(xml_stream)
                self.update_end_balances(grouped_data)
            elif response_data['status_code'] != sb.EXTERNAL_FAILURE:
                error = '[{}] / {}'.format(response_data['status_code'], response_data['system_notification'])
                raise exceptions.ValidationError(_('SEB API: Balance parsing error: {}').format(error))

    @api.model
    def api_fetch_transactions_prep(self, journal, date_from, date_to, fetch_job):
        """
        Method that prepares transaction fetching for specific
        SEB journal - creates separate thread which calls statement
        fetching. Called manually
        :param journal: account.journal record
        :param date_from: date_from (str)
        :param date_to: date_to (str)
        :param fetch_job: Statement fetch job record
        :return: result of query_statements()
        """

        # Convert the dates from datetime format to date format
        if date_from:
            date_from = convert_date(date_from)

        if date_to:
            date_to = convert_date(date_to)

        # Start the threaded calculations
        threaded_calculation = threading.Thread(
            target=self.api_fetch_transactions_threaded, args=(journal.id, date_from, date_to, fetch_job.id))
        threaded_calculation.start()

    @api.model
    def api_fetch_transactions_threaded(self, journal_id, date_from, date_to, fetch_job_id):
        """
        Intermediate method that executes 'api_fetch_transactions' method
        in a thread. If 'api_fetch_transactions' catches an exception,
        robo.bug is created.
        :param journal_id: account.journal ID for which the transactions are fetched
        :param date_from: date from
        :param date_to: date to
        :param fetch_job_id: Statement fetch job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = self.with_env(self.env(cr=new_cr, user=odoo.SUPERUSER_ID)).env

            # Get the needed records
            fetch_job = env['bank.statement.fetch.job'].browse(fetch_job_id)
            journal = env['account.journal'].browse(journal_id)
            fetching_state, error_message = 'succeeded', str()
            try:
                # Check whether API is correctly configured
                configuration = env['seb.api.base'].get_configuration(raise_exception=False)
                # Manual action here, thus we just raise
                if not configuration.statement_endpoint:
                    raise exceptions.ValidationError(
                        _("Bank statement functionality is not activated in client's SEB integration")
                    )
                # Try to fetch the statements
                env['seb.api.base'].with_context(fetch_job_id=fetch_job_id).api_fetch_transactions(
                    journal, date_from, date_to)
            except Exception as exc:
                new_cr.rollback()
                fetching_state = 'failed'
                error_message = _('Išrašų traukimo klaida - {}').format(exc.args[0] if exc.args else str())

            fetch_job.close_statement_fetch_job(fetching_state, error_message)
            # Commit the changes and close the cursor
            new_cr.commit()
            new_cr.close()

    @api.model
    def api_fetch_transactions(self, journals=None, date_from=None, date_to=None):
        """
        Method that calls recursive method to fetch bank statements for each
        active SEB journal with correct IBAN, given period of date_from and date_to.
        If date_to is not specified current time is used instead,
        and if date_from is not specified as well, EOD (end-of-day) transactions
        for previous day is called
        :param date_from: Period date from
        :param date_to: Period date to
        :param journals: account.journal record/set (optional, if not provided, transactions
            are fetched for every SEB journal in the system)
        :return: None
        """

        # Check whether API is correctly configured
        configuration = self.get_configuration(raise_exception=False)
        if not configuration.check_configuration() or not configuration.statement_endpoint:
            return

        # Use either passed journal or all of the other SEB journals
        acc_journals = configuration.get_related_journals() if journals is None else journals
        seb_to_account_journal_mapping = {k.journal_id: k for k in configuration.seb_journal_ids}
        # Determine the action based on the date_from
        action = 'get_period_statements'
        if not date_from:
            action = 'get_day_before_statements'
        statement_periods = []
        # If action is for specific period, update the dict with date values
        if action == 'get_period_statements':
            # Strip trailing time information and convert date strings to datetime objects
            date_from = convert_date(date_from)
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            # Prepare date to if it exists, otherwise use day before current
            if date_to:
                date_to = convert_date(date_to)
                date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                date_to_dt = datetime.utcnow() - relativedelta(days=1)

            # If delta is bigger than max statement day period, split the days
            delta = (date_to_dt - date_from_dt).days
            if delta > sb.MAX_STATEMENT_DAY_PERIOD:
                while date_from_dt < date_to_dt:
                    # Calculate days to add - minimum of the updated delta or period
                    days_to_add = min((date_to_dt - date_from_dt).days, sb.MAX_STATEMENT_DAY_PERIOD)
                    temp_dt_end = date_from_dt + relativedelta(days=days_to_add)
                    statement_periods += [(
                        date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                        temp_dt_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    )]
                    date_from_dt = temp_dt_end + relativedelta(days=1)
            else:
                # Prepare the tuple of dates
                statement_periods += [(
                    date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                )]
        else:
            # Fill the data with dummies if its EOD fetch
            statement_periods += [(str(), str())]

        transaction_files = []
        # Loop through journals and get the data
        for journal in acc_journals:
            # Validate the IBAN
            j_iban = journal.bank_acc_number
            try:
                validate_iban(j_iban)
            except exceptions.ValidationError:
                raise exceptions.UserError(_('SEB API: Incorrect IBAN number - {}!').format(j_iban))
            # Loop through period statements
            for date_from, date_to in statement_periods:
                # Prepare the extra data
                extra_data = {'object_id': j_iban, 'limit': sb.API_RECORD_LIMIT, }
                if date_from and date_to:
                    extra_data.update({'d_from': date_from, 'd_to': date_to, })
                # Call the API endpoint
                successful_call, response_data = self.call(
                    action=action, extra_data=extra_data,
                )
                repeat_action = response_data.get('repeat_action')
                # Mark EOD re-fetch boolean if necessary
                if action == 'get_day_before_statements':
                    # If current account journal is not in the seb-to-account mapping,
                    # just re-search the journal. Occurs when called from manual wizard
                    seb_journal = seb_to_account_journal_mapping.get(journal)
                    if not seb_journal:
                        seb_journal = self.env['seb.api.journal'].search([('journal_id', '=', journal.id)])
                    seb_journal.write({'retry_eod_transaction_fetch': repeat_action})
                if successful_call:
                    transaction_files.append(response_data['xml_stream'])
                else:
                    # If error is not 500, we raise an error
                    if not response_data.get('external_failure') and not repeat_action:
                        raise exceptions.ValidationError(_(response_data['system_notification']))

        # Try to process fetched files
        if transaction_files:
            self.process_transaction_files(transaction_files)

    @api.model
    def api_push_bank_statements(self, prep_data):
        """
        Method that is used to prepare data for the API call.
        Checks basic constraints and determines whether
        API thread should be used or not.
        :param prep_data: grouped transaction data (dict)
        :return: None
        """

        # Check whether API is correctly configured
        configuration = self.get_configuration(raise_exception=False)
        if not configuration.check_configuration() or not configuration.payment_init_endpoint:
            return

        related_exports = prep_data['bank_exports']
        # Call the endpoint to submit the file for processing
        successful_call, response_data = self.call(
            action='post_unsigned_payment',
            extra_data={'raw_xml': prep_data['xml_stream']},
            manual_action=True,
        )
        # On successful call, call the method to get the states
        if successful_call:
            xml_obj = response_data.get('xml_obj')
            if xml_obj and hasattr(xml_obj, 'paymentFileId'):
                # Get the payment file ID and write it to the exports
                payment_file_id = self.parse(xml_obj.paymentFileId, str)
                related_exports.write({'api_external_id': payment_file_id})
                # Call the method to update the payment states
                self.api_fetch_payment_states(payment_file_id, related_exports, manual_action=True)
            else:
                raise exceptions.ValidationError(
                    _('Failed to push the statements to SEB bank - '
                      'incorrect response structure, contact system administrators')
                )
        else:
            # Initial push was rejected, it means it's not the data issue thus
            # states should not be updated, error should be displayed
            status_description = response_data.get('status_description', str())
            sys_msg = response_data.get('system_notification', str())
            _logger.info('SEB API: Payment submition error - {}'.format(sys_msg))

            # Check whether API error was in 'forbidden' codes,
            # if so, deactivate payment init endpoint
            self.env.cr.rollback()
            if response_data['status_code'] in sb.FORBIDDEN:
                configuration.payment_init_endpoint = False
            self.env.cr.commit()

            raise exceptions.ValidationError(
                _('Failed to push the payments to SEB bank. '
                  'Repeat the steps and contact the adminsitrators if it persists. '
                  'Error message:\n {}'.format(status_description))
            )

        # Initiate payment transfer wizard, which displays the statuses of just-exported statements
        transfer_wizard = self.env['seb.payment.transfer.wizard'].create({
            'bank_export_job_ids': [(4, x.id) for x in related_exports]
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'seb.payment.transfer.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'res_id': transfer_wizard.id,
            'view_id': self.env.ref('sepa.form_seb_payment_transfer_wizard').id,
        }

    @api.model
    def api_fetch_payment_states(self, ext_id, exports, manual_action=False):
        """
        Fetches payment state data for current file ID
        :param ext_id: external ID of the export (batch)
        :param exports: bank export job records
        :param manual_action: Indicates whether action was executed
        by cron job or by the user (boolean)
        :return: None
        """

        export_state = 'rejected'
        successful_call, response_data = self.call(
            action='get_payment_status_report',
            extra_data={'object_id': ext_id},
            manual_action=manual_action,
        )
        if successful_call:
            # Fetch xml stream, and process it on successful call
            xml_stream = response_data.get('xml_stream', str())
            export_data = self.process_payment_response(xml_stream)
            self.update_export_states(export_data, exports, manual_action=manual_action)
        else:
            status_description = response_data.get('status_description', str())
            sys_msg = response_data.get('system_notification', str())
            # Always log the messages
            _logger.info('SEB API: encountered external server error while updating states - {}'.format(sys_msg))

            # Get the retry threshold for exports
            retry_threshold = self.sudo().env['ir.config_parameter'].get_param('seb_state_update_retry_count')
            try:
                retry_threshold = int(retry_threshold)
            except (ValueError, TypeError):
                pass
            if not retry_threshold or not isinstance(retry_threshold, int):
                retry_threshold = 3  # DEFAULT VALUE

            export_values = {
                'export_state': export_state,
                'last_error_message': status_description,
                'system_notification': sys_msg,
            }
            exports_to_update = self.env['bank.export.job']
            # If failure is not external update the exports
            if response_data.get('external_failure') or response_data.get('repeat_action'):
                # If failure is external or repeat action flag is passed,
                #  loop through exports and post only to those that have more than x update retries
                for export in exports:
                    if export.state_update_retries >= retry_threshold:
                        exports_to_update |= export
                    else:
                        # Increment the counter of retries
                        export.write({'state_update_retries': export.state_update_retries + 1})
            else:
                exports_to_update = exports
            # Update the exports
            exports_to_update.write(export_values)
            exports_to_update.post_message_to_related(status_description)

    # -----------------------------------------------------------------------------------------------------------------
    # API Core --------------------------------------------------------------------------------------------------------

    @api.model
    def call(self, action, extra_data=None, manual_action=False):
        """
        Main method used to prepare data/structures for SEB API call.
        :return: True/False (based on success of the call), response_data
        """
        # Get the required data and call the endpoint
        api_data = self.get_api_endpoint_data(action, extra_data=extra_data)
        response = self.call_api_endpoint(api_data)

        # Sanitize the response, parse the data and status code
        response_data, status_code = self.sanitize_api_response(action, response, manual_action)

        # Check whether call was successful
        successful_call = status_code == 200
        return successful_call, response_data

    @api.model
    def call_api_endpoint(self, api_data):
        """
        Method used to generate authentication key and call specific SEB API endpoint.
        Call is authenticated by using specific SEB certificate which is stored in server.
        :param api_data: dict {request_endpoint, request_method, request_url, data, data_type}
        :return: response of specific API endpoint (object)
        """

        req_method = api_data['request_method']
        request_url = api_data['request_url']

        # Get SEB certificate file path
        cert_path = self.sudo().env['ir.config_parameter'].get_param('seb_cert_path')
        if not cert_path:
            error = _('SEB API: Certificate file path is not specified.')
            if not self.env.user.has_group('base.group_system'):
                error += _('\n Contact administrators')
            raise exceptions.ValidationError(error)

        if not os.path.isfile(cert_path):
            error = _('SEB API: Certificate file was not found.')
            if not self.env.user.has_group('base.group_system'):
                error += _('\n Contact administrators')
            raise exceptions.ValidationError(error)

        # Get origin ID from configuration record
        configuration = self.get_configuration(raise_exception=False)
        org_id = configuration.organisation_id

        # Base header data that is the same for POST/GET
        base_headers = {'orgid': org_id, 'accept': 'application/xml', 'content-type': 'application/xml;charset=UTF-8'}
        try:
            # Initiate the request
            if req_method == 'GET':
                # Call the endpoint
                response = requests.get(request_url, headers=base_headers, cert=cert_path)
            else:
                # Build data hash
                encoded_data = json.dumps(api_data['data'])
                data_hash = str(base64.b64encode(hashlib.sha256(encoded_data).digest()).decode())

                # Build POST headers
                post_headers = base_headers.copy()
                post_headers.update({
                    'idempotency-key': data_hash,
                })
                # Call the endpoint
                response = requests.post(
                    request_url, headers=post_headers,
                    cert=cert_path, data=api_data['data']['raw_xml'],
                )
        except requests.exceptions.SSLError as e:
            _logger.info('SEB API SSL ERROR: {}'.format(e.args[0]))
            raise exceptions.ValidationError(
                _('Could not reach SEB server due to certificate issues. Please contact administrators')
            )
        return response

    @api.model
    def get_api_endpoint_data(self, action, extra_data=None):
        """
        Prepare specific SEB API endpoint based on passed action value
        :param action - api endpoint in scoro system
        :param extra_data - extra parameters that are passed to the endpoint
        :return formatted message
        """

        extra_data = {} if extra_data is None else extra_data

        # SEB endpoint url that is
        # mapped to action in our system
        endpoint_mapping = {
            # No explicit method to take the balance, thus we fetch current
            # transaction file and self.parse the balance from there
            'get_balance': '/v1/accounts/{object_id}/current-transactions',
            'get_day_before_statements': '/v1/accounts/{object_id}/eod-transactions',
            'get_period_statements': '/v1/accounts/{object_id}/transactions?from={d_from}&to={d_to}&size={limit}',
            'post_unsigned_payment': '/v1/testing-payment-files',
            'post_signed_payment': '/v1/signed-payment-files',
            'get_payment_status': '/v1/payment-initiations/{object_id}',
            'get_payment_status_report': '/v1/payment-initiations/{object_id}/pain002',
            'post_payment_cancel': '/v1/payment-initiations/{object_id}/cancellation',
        }

        # SEB method (GET, POST) based on action in our system
        method_mapping = {
            'get_balance': 'GET',
            'get_day_before_statements': 'GET',
            'get_period_statements': 'GET',
            'post_unsigned_payment': 'POST',
            'post_signed_payment': 'POST',
            'get_payment_status': 'GET',
            'get_payment_status_report': 'GET',
            'post_payment_cancel': 'POST',
        }

        # Indicates what actions expect JSON data
        json_actions = ['post_payment_batch', 'post_payment_cancel']

        # Gets method, endpoint, and other info
        # based on the action
        endpoint = endpoint_mapping.get(action)
        method = method_mapping.get(action)
        json_data = action in json_actions

        # If not method or endpoint exists, raise an exception
        if not endpoint or not method:
            raise exceptions.ValidationError(_('Incorrect endpoint is passed!'))

        # Format the endpoint
        endpoint = endpoint.format(**extra_data)
        base_url = self.sudo().env['ir.config_parameter'].get_param('seb_api_url')
        if not base_url:
            base_url = sb.STATIC_SEB_URL

        req_url = 'https://{}{}'.format(base_url, endpoint)
        return {
            'request_url': req_url,
            'request_endpoint': endpoint,
            'request_method': method,
            'data': extra_data,
            'json_data': json_data
        }

    @api.model
    def sanitize_api_response(self, action, response, manual_action):
        """
        Sanitize the response of specific SEB API endpoint
        :param action: action method (string)
        :param response: response object
        :param manual_action: Indicates whether action is done by a job, or manually
        :return: response content (dict), status code (int)
        """
        # Parse the JSON and get status code
        try:
            response_content = {
                'xml_obj': objectify.fromstring(response.content),
                'xml_stream': response.content,
            }
            status_code = response.status_code
        except (ValueError, AttributeError):
            response_content = {}
            status_code = 500

        ext_e_code = error_str = description = str()
        # If status code is not 200, raise an error (or send a bug)
        if status_code != 200:

            # Check whether response content contains any tag, if it does, we can parse the error
            if response_content.get('xml_obj') and hasattr(response_content['xml_obj'], 'code'):
                ext_e_code = self.parse(response_content['xml_obj'].code, str)

            description = sb.GENERAL_API_RESPONSE_MAPPING.get(status_code, _('Unexpected error'))
            # Compose an error message
            error_str = _('SEB API error: {}\nDescription: {}\nStatus code - [{}]').format(
                ext_e_code, description, status_code,
            )
            _logger.info(error_str)

            # Check whether error should be raised based on action and external code
            non_raise_errors = sb.NON_RAISE_ACTION_TO_RESP_MAPPING.get(action)
            no_raise = non_raise_errors and ext_e_code in non_raise_errors

            # Check no raises by status code
            if not no_raise:
                non_raise_statuses = sb.NON_RAISE_ACTION_TO_CODE_MAPPING.get(action)
                no_raise = non_raise_statuses and status_code in non_raise_statuses

            if status_code == 500:
                response_content['external_failure'] = True
            if no_raise:
                response_content['repeat_action'] = True

            if not manual_action and not no_raise and status_code != 500:
                raise exceptions.ValidationError(error_str)

        # Always attach detailed admin error to the response
        response_content.update({
            'system_notification': error_str,
            'status_description': description,
            'status_code': status_code,
        })
        return response_content, status_code

    # -----------------------------------------------------------------------------------------------------------------
    # Processing Methods ----------------------------------------------------------------------------------------------

    @api.model
    def process_transaction_files(self, file_data_list):
        """
        Processes passed transaction files -- SEPA import
        wizard is called for each file.
        :param file_data_list: list of XML string values
        :return: None
        """

        # Check whether fetch job is passed in the context
        fetch_job = self.env['bank.statement.fetch.job']
        fetch_job_id = self._context.get('fetch_job_id')
        # If fetch job was passed via context, search for the actual record
        if fetch_job_id:
            fetch_job = fetch_job.browse(fetch_job_id).exists()
        transaction_processing_errors = str()
        for file_data in file_data_list:
            try:
                # Encode the file and pass it to the wizard to self.parse
                file_b64 = base64.encodestring(file_data)
                # Update fetch job if file does not exist
                if fetch_job and not fetch_job.fetched_file:
                    fetch_job.write({
                        'fetched_file': file_b64,
                        'fetched_file_name': 'SEB Statement.xml',
                    })
                self.env.cr.commit()
                wizard = self.env['account.sepa.import'].create({
                    'coda_data': file_b64,
                    'skip_currency_rate_checks': True,
                })
                wizard.coda_parsing()
            except Exception as e:
                transaction_processing_errors += '{}\n'.format(e.args[0])
                self.env.cr.rollback()
        # Send a bug report or raise an error
        if transaction_processing_errors:
            if fetch_job:
                # Manually raise the error if fetch job is passed, since calling method
                # is try-excepting this output, and it formats it nicely
                raise exceptions.ValidationError(
                    _('Bankinio išrašo užklausa nepavyko: {}').format(transaction_processing_errors)
                )
            body = 'SEB API: Failed to process transaction files with following errors - {}\n\n'.format(
                transaction_processing_errors)
            subject = 'SEB API Bug [{}]'.format(self.env.cr.dbname)
            self.env['script'].send_email(emails_to=['support@robolabs.lt'], body=body, subject=subject)

    @api.model
    def process_balance_response(self, xml_data):
        """
        Processes SEB balance response XML file - fetches the balances
        and update dates. Data is grouped by journals and currencies.
        :param xml_data: XML file data str
        :return: grouped data dict
        """

        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', 'xsd_schemas')) + '/camt.052.001.02.xsd'

        # Validate the balance XML
        validated, error = abi.xml_validator(xml_data, path)
        if not validated:
            raise exceptions.ValidationError(_('SEB API: Received incorrect balance file'))

        try:
            # Try to parse the root node
            root = etree.fromstring(xml_data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            raise exceptions.ValidationError(_('SEB API: Received incorrect balance file'))

        try:
            # Parse the tag value from the root node
            ns = root.tag[1:root.tag.index("}")]
            path = str('{' + ns + '}')
        except Exception as exc:
            raise exceptions.ValidationError(
                _('SEB API: Received incorrect balance file. Error {}').format(exc.args[0])
            )

        # Find all RPT vals
        rpt_vals = root.findall('.//' + path + 'BkToCstmrAcctRpt/' + path + 'Rpt')
        if rpt_vals is None:
            raise exceptions.ValidationError(_('SEB Bank API: Received malformed balance file'))

        # Prepare the structure to group the IBAN's and their balance data
        grouped_data = {}
        # Loop through RPT values
        for rpt_val in rpt_vals:
            acct = rpt_val.find(path + 'Acct')

            # Check the IBAN of the journal
            journal_iban = self.parse(acct.find(path + 'Id/' + path + 'IBAN'), str)
            # Get the balance date
            balance_date = self.parse(rpt_val.find(path + 'CreDtTm'), str)

            # Set default for current IBAN
            grouped_data.setdefault(journal_iban, {})

            # Loop through balance nodes and only fetch ITAV balance
            bal_vals = rpt_val.findall(path + 'Bal')
            for bal_val in bal_vals:
                # Get the balance type
                bal_tp_n = bal_val.find(path + 'Tp/' + path + 'CdOrPrtry/' + path + 'Prtry')
                if bal_tp_n is None:
                    bal_tp_n = bal_val.find(path + 'Tp/' + path + 'CdOrPrtry/' + path + 'Cd')
                bal_tp = self.parse(bal_tp_n, str())

                # If balance type is not ITAV (current balance with all reservations)
                # just skip current iteration
                if bal_tp != 'ITAV':
                    continue

                # Get the currency of the statement
                currency_code = 'EUR'
                if bal_val.find(path + 'Amt') is not None:
                    currency_code = bal_val.find(path + 'Amt').attrib.get('Ccy')

                # Append the data to the group
                grouped_data[journal_iban][currency_code] = {
                    'api_end_balance': self.parse(bal_val.find(path + 'Amt'), int),
                    'api_balance_update_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                }

        return grouped_data

    @api.model
    def process_payment_response(self, xml_data):
        """
        Processes SEB payment (pain.002) response XML file - parses the transaction
        states and returns the dictionary with grouped bank statement jobs.
        :param xml_data: XML file data str.
        :return: grouped data dict
        """

        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', 'xsd_schemas')) + '/pain.002.001.03.xsd'

        # Basic error messages
        parsing_error = _('SEB API: Could not parse payment response file.')
        structure_error = _('SEB API: Received malformed payment response file.')

        export_objects = {}
        # Validate the pain.002 response XML
        validated, error = abi.xml_validator(xml_data, path)
        if not validated:
            raise exceptions.ValidationError(parsing_error)
        try:
            # Try to parse the root node
            root = etree.fromstring(xml_data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            raise exceptions.ValidationError(parsing_error)
        try:
            # Parse the tag value from the root node
            ns = root.tag[1:root.tag.index("}")]
            path = str('{' + ns + '}')
        except Exception as exc:
            raise exceptions.ValidationError(
                parsing_error + _(' Error {}').format(exc.args[0])
            )
        try:
            # Check whether status report nodes exist
            status_report = root.find('.//' + path + 'CstmrPmtStsRpt/' + path + 'OrgnlGrpInfAndSts')
            if status_report is None:
                raise exceptions.ValidationError(structure_error)

            # Check for payment status nodes
            payment_status = status_report.find(path + 'GrpSts')
            if payment_status is None:
                status_report = root.find('.//' + path + 'CstmrPmtStsRpt/' + path + 'OrgnlPmtInfAndSts')
                payment_status = status_report.find(path + 'PmtInfSts')
            if payment_status is None:
                raise exceptions.ValidationError(structure_error)

            parent_state = self.parse(payment_status, str)
            transaction_reports = root.findall(
                './/' + path + 'CstmrPmtStsRpt/' + path + 'OrgnlPmtInfAndSts/' + path + 'TxInfAndSts')

            for tr_report in transaction_reports:
                export_id = self.parse(tr_report.find(path + 'OrgnlInstrId'), str)
                # Tr state is used, however parent state must exist
                tr_state = parent_state and self.parse(tr_report.find(path + 'TxSts'), str)

                # Map sepa state to the system state
                sys_state = 'accepted'
                if tr_state in abi.EXTERNAL_SEPA_REJECTED_STATES:
                    sys_state = 'rejected'
                elif tr_state in abi.EXTERNAL_SEPA_PROCESSED_STATES:
                    sys_state = 'processed'

                # Fetch the error message based on state
                error_message = str()
                if tr_state in abi.EXTERNAL_SEPA_REJECTED_STATES:
                    error_message = self.parse(tr_report.find(path + 'StsRsnInf/' + path + 'AddtlInf'), str)
                export_objects[export_id] = {
                    'state': tr_state,
                    'sys_state': sys_state,
                    'error_message': error_message,
                }
        except Exception as exc:
            _logger.info('SEB API: Payment response exception {}'.format(exc.args[0]))
            raise exceptions.ValidationError(structure_error)
        return export_objects

    @api.model
    def update_export_states(self, data, bank_exports, manual_action=False):
        """
        Updates states of currently passed bank export
        batch based on sepa instruction ID.
        :param data: dict of state data
        :param bank_exports: bank export job records
        :param manual_action: Indicates whether action was executed
        by cron job or by the user (boolean)
        :return: None
        """
        for ext_id, export_data in data.items():
            related_exports = bank_exports.filtered(lambda x: x.sepa_instruction_id == ext_id)
            system_state = export_data.get('sys_state')
            error_message = export_data.get('error_message')
            for export in related_exports:
                # If payment is partial, get the partial state
                if export.partial_payment:
                    system_state = '{}_partial'.format(system_state)
                # Write the state to related export record
                export.write({'export_state': system_state, 'last_error_message': error_message})

                inform_errors = str()
                if system_state in ['rejected', 'rejected_partial'] and not manual_action:
                    # Inform user or post to object on state change (Invoices)
                    if export.invoice_ids:
                        inform_errors += _('Invoices: {}\n').format(', '.join(export.invoice_ids.mapped('number')))
                    # Inform user or post to object on state change (AMLs/Moves)
                    if export.move_line_ids:
                        inform_errors += _('Journal entries: {}\n').format(
                            ', '.join(export.move_line_ids.mapped('name'))
                        )
                    # Inform user or post to object on state change (Front statement)
                    if export.front_statement_line_id:
                        inform_errors += _('Front statement line: {}').format(export.front_statement_line_id.name)

                    # Inform the user that exported the payment about it's statuses
                    if inform_errors:
                        email_body = _(
                            'Payment export to SEB bank was rejected. Related objects - {}\n\n'
                        ).format(inform_errors)
                        subject = '{} // [{}]'.format(_('SEB Payment export -- rejected'), self.env.cr.dbname)
                        self.env['script'].send_email(
                            emails_to=[export.partner_id.email],
                            subject=subject, body=email_body
                        )
            # Post the messages to related objects
            related_exports.post_message_to_related()

    @api.model
    def update_end_balances(self, data):
        """
        Updates related journal balances based on API
        fetched data. If journal does not exist, and
        new currency was received - it's created
        :param data: dict of grouped balance data
        :return: None
        """

        # Default values
        company_currency = self.env.user.company_id.currency_id
        journal_ob = self.sudo().env['account.journal']
        res_bank = self.env['res.bank'].search([('bic', '=', abi.SEB_BANK)])

        # Currency grouping dict - by currency code
        currencies = {}
        # Loop through grouped data and update the balances
        for account_iban, by_currency in data.items():
            for currency_code, balance_info in by_currency.items():
                # Find related currency in the system
                if currency_code not in currencies:
                    currency = self.env['res.currency'].search([('name', '=', currency_code)])
                    if not currency:
                        # Ensure that currency exists in the system
                        raise exceptions.ValidationError(
                            _('SEB API: Received {} currency from the API, however it does not exist in the system')
                        )
                    currencies[currency_code] = currency
                currency_rec = currencies[currency_code]

                end_balance = balance_info['api_end_balance']
                # Build a domain, if company currency differs
                # from IBAN currency, add it to search domain
                domain = [('bank_acc_number', '=', account_iban), ('type', '=', 'bank')]
                if currency_rec.id != company_currency.id:
                    domain += [('currency_id', '=', currency_rec.id)]
                else:
                    domain += ['|', ('currency_id', '=', company_currency.id), ('currency_id', '=', False)]
                journal = journal_ob.search(domain, limit=1)

                # If journal does not exist, create it (only if end balance is not zero)
                if not journal and not tools.float_is_zero(end_balance, precision_digits=2):
                    code = journal_ob.get_journal_code_bank()
                    journal_vals = {
                        'name': '%s (%s) %s' % (res_bank.name, account_iban[-4:], currency_rec.name),
                        'code': code,
                        'bank_statements_source': 'file_import',
                        'type': 'bank',
                        'company_id': self.env.user.company_id.id,
                        'bank_acc_number': account_iban,
                        'bank_id': res_bank.id,
                    }
                    if currency_rec.id != company_currency.id:
                        journal_vals.update({'currency_id': currency_rec.id})
                    journal = journal_ob.create(journal_vals)

                if journal:
                    # Update the journal with received data
                    journal.write({
                        'api_end_balance': end_balance,
                        'api_balance_update_date': balance_info['api_balance_update_date'],
                    })

    # -----------------------------------------------------------------------------------------------------------------
    # Utility Methods -------------------------------------------------------------------------------------------------

    @api.model
    def parse(self, node, expected_type, date=False):
        """Returns XML node's text"""
        if node is not None:
            return node.text.replace('T', ' ') if date else node.text
        else:
            if date:
                return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            elif expected_type is int:
                return 0
            elif expected_type is str:
                return str()

    @api.model
    def get_configuration(self, raise_exception=True):
        """Return SEB MAC configuration record after validating"""
        configuration = self.env['seb.configuration'].search([])
        if not configuration and raise_exception:
            raise exceptions.ValidationError(_('SEB configuration record was not found!'))
        return configuration

    # -----------------------------------------------------------------------------------------------------------------
    # Cron Jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_fetch_end_balances(self):
        """
        Cron that fetches end balances for each SEB journal
        :return: None
        """
        # Don't run balance fetching at night
        # some cron-jobs are delayed by the server load balancer
        # thus it has big possibility to intersect
        current_hour = datetime.now(pytz.timezone('Europe/Vilnius')).hour
        if current_hour > 7 or current_hour < 3:
            self.api_fetch_end_balances()

    @api.model
    def cron_update_export_states(self):
        """
        Cron that updates the states of pending exported SEB payments
        :return: None
        """
        # Check configuration of the integration
        configuration = self.get_configuration(raise_exception=False)
        if not configuration.check_configuration() or not configuration.payment_init_endpoint:
            return

        # Get all the pending exports for seb journals
        acc_journals = configuration.get_related_journals(include_error=True)
        bank_exports = self.env['bank.export.job'].search([
            ('journal_id', 'in', acc_journals.ids),
            ('export_state', '=', 'waiting'),
            ('xml_file_download', '=', False),
        ])
        # Build export mapping by ext file ID
        exports_by_ext_id = {}
        for export in bank_exports:
            e_id = export.api_external_id
            exports_by_ext_id.setdefault(e_id, self.env['bank.export.job'])
            exports_by_ext_id[e_id] |= export

        # Update the states of each JOB
        for ext_id, exports in exports_by_ext_id.items():
            self.api_fetch_payment_states(ext_id, exports)

    @api.model
    def cron_retry_eod_transaction_fetch(self):
        """
        Cron that runs every hour as opposed to
        daily run and checks whether EOD transaction
        fetch should be retried.
        :return: None
        """
        configuration = self.get_configuration(raise_exception=False)
        re_fetch_journals = configuration.seb_journal_ids.filtered(
            lambda x: x.retry_eod_transaction_fetch and x.activated
        ).mapped('journal_id')
        if re_fetch_journals:
            self.api_fetch_transactions(journals=re_fetch_journals)

    @api.model
    def cron_fetch_statements_daily(self):
        """
        Cron that fetches daily bank statements for SEB accounts
        :return: None
        """
        # No need to pass any date from, EOD for previous day will be called
        self.api_fetch_transactions()

    @api.model
    def cron_fetch_statements_weekly(self):
        """
        Cron that fetches weekly bank statements for SEB accounts
        :return: None
        """
        date_from = (datetime.now() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.api_fetch_transactions(date_from=date_from)

    @api.model
    def cron_fetch_statements_monthly(self):
        """
        Cron that fetches monthly bank statements for SEB accounts
        :return: None
        """
        date_from = (datetime.now() - relativedelta(day=1, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.api_fetch_transactions(date_from=date_from)
