# -*- encoding: utf-8 -*-
from __future__ import division
from odoo import models, _, api, exceptions, tools
from collections import OrderedDict
from odoo.api import Environment
from datetime import datetime
from requests import ConnectionError
from dateutil.relativedelta import relativedelta
from ... import api_bank_integrations as abi
from .. import paysera_tools as pt
from unidecode import unidecode
from six import iteritems
import pytz
import logging
import threading
import odoo
import time
import string
import random
import hmac
import hashlib
import base64
import requests
import json
import urllib

_logger = logging.getLogger(__name__)
API_THROTTLING_PERIOD_SPLIT = {
    3: {'days': 1},
    2: {'hours': 1},
    1: {'minutes': 10},
}


class PayseraAPIBase(models.AbstractModel):
    _name = 'paysera.api.base'

    # -----------------------------------------------------------------------------------------------------------------
    # API actions -----------------------------------------------------------------------------------------------------

    # Statement export-to-bank methods --------------------------------------------------------------------------------

    @api.model
    def api_sign_bank_statement(self, bank_export):
        """
        Method that is used to sign specific bank export object.
        Constrains that either allow or deny signing are checked,
        as well as external_signing_daily_limit_residual amount
        :param bank_export: bank.export.job object
        :return: None
        """
        configuration = self.env['paysera.api.base'].get_configuration()
        e_sign_residual = configuration.sudo().external_signing_daily_limit_residual

        # Explicit addition check for signing allowing
        if not configuration.sudo().allow_external_signing:
            raise exceptions.ValidationError(_('Transaction signing is not enabled in the company!'))

        # Check if current transaction can be made (limit checks)
        post_sign_residual = e_sign_residual - bank_export.tr_amount
        if tools.float_compare(0.0, post_sign_residual, precision_digits=2) > 0:
            raise exceptions.ValidationError(_('Daily transaction signing amount limit is exceeded!'))

        # Call the endpoint to fetch token data
        successful_call, response_data = self.env['paysera.api.base'].call(
            action='sign_transfer',
            forced_mac_key=self.get_mac_key(endpoint_group='transfers'),
            forced_client_id=self.get_client_id(endpoint_group='transfers'),
            extra_data={'object_id': bank_export.api_external_id},
        )
        # Depending on the success of the call, write the values,
        # commit changes and raise an error as a display
        # (ALWAYS CALLED FROM A FORM AS A MANUAL ACTION)
        if successful_call:
            configuration.sudo().write({
                'external_signing_daily_limit_residual': post_sign_residual,
            })
            bank_export.write({
                'e_signed_export': True,
                'export_state': 'processed_partial' if bank_export.partial_payment else 'processed',
                'date_signed': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            })
            self.env.cr.commit()
            raise exceptions.ValidationError(_('Transaction was signed successfully!'))
        else:
            error = _('Failed to sign the transaction')
            bank_export.write({
                'export_state': 'rejected_sign',
                'last_error_message': error + _(' Error message - {}').format(response_data['error'])
            })
            self.env.cr.commit()
            raise exceptions.ValidationError(error)

    @api.model
    def api_push_bank_statements(self, transaction_data):
        """
        Method that is used to prepare data for the API call.
        Checks basic constraints and determines whether
        API thread should be used or not.
        :param transaction_data: grouped transaction data (dict)
        :return: None
        """

        # Check whether API is correctly configured
        if not self.sudo().check_configuration(fully_functional=True):
            return

        batch_exports = transaction_data.get('batch_exports', [])
        journal = transaction_data.get('journal_id')

        # Try to find related wallet of the journal
        related_wallet = self.env['paysera.wallet'].sudo().get_related_wallet(journal)
        if not (related_wallet.user_name or related_wallet.user_code or related_wallet.user_type):
            raise exceptions.ValidationError(_('Required wallet information is not configured!'))

        # If size of the set is bigger than the static value, use the thread
        if len(batch_exports) > pt.NON_THREADED_RECORD_SIZE:
            threaded_calculation = threading.Thread(
                target=self.action_push_statements_threaded, args=(transaction_data, related_wallet, ))
            threaded_calculation.start()
        else:
            return self.action_push_statements(transaction_data, related_wallet)

    @api.model
    def action_push_statements_threaded(self, transaction_data, related_wallet):
        """
        Intermediate method that executes 'action_push_statements' method
        in a thread. If 'action_push_statements' catches an exception,
        robo.bug is created, also all batch exports are immediately rejected
        :param transaction_data: grouped transaction data (dict)
        :param related_wallet: related paysera.wallet record
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = self.with_env(self.env(cr=new_cr, user=odoo.SUPERUSER_ID)).env
            try:
                # Try to push the statements
                env['paysera.api.base'].action_push_statements(transaction_data, related_wallet)
            except Exception as exc:
                new_cr.rollback()
                # On exception changes are rollback-ed, and robo bug is created
                transaction_data['batch_exports'].write({
                    'state': 'rejected',
                    'error_message': _('Unexpected API error, contact system administrators.')
                })
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': exc.args[0] if exc.args else 'Unexpected error',
                    'subject': 'Paysera Integration Error -- Statement export [%s]' % self._cr.dbname,
                })
        # Commit the changes and close the cursor
        new_cr.commit()
        new_cr.close()

    @api.model
    def action_push_statements(self, transaction_data, related_wallet):
        """
        Method that pushes statement data to Paysera API endpoint.
        Data is grouped for the endpoint accepted format,
        all mandatory constraints are validated
        :param transaction_data: grouped transaction data (dict)
        :param related_wallet: related paysera.wallet record
        :return: None
        """

        company_currency = self.sudo().env.user.company_id.currency_id
        batch_exports = transaction_data.get('batch_exports', [])
        international_priority = transaction_data.get('international_priority')

        # Prepare global payer block
        payer_block = {'account_number': related_wallet.paysera_account_number}

        forced_mac_key = self.get_mac_key(endpoint_group='transfers')
        forced_client_id = self.get_client_id(endpoint_group='transfers')

        # Loop through lines and build data dict
        for line in batch_exports:
            line_level_errors = str()

            urgency = 'standard' if not international_priority or international_priority == 'NURG' else 'urgent'
            # Check constraints and prepare amount block
            if tools.float_is_zero(line.tr_amount, precision_digits=2):
                line_level_errors += _('You cannot export zero amount.\n')
            line_currency = line.tr_currency_id.name or company_currency.name
            if not line_currency:
                line_level_errors += _('Currency was not found.\n')

            # Always ABS the amount! Paysera does not accept negative numbers
            amount_block = {'amount': abs(line.tr_amount), 'currency': line_currency}
            partner = line.tr_partner_id
            # Check constraints and prepare beneficiary block
            if not line.tr_bank_account_id:
                line_level_errors += _('Beneficiary bank account is not specified.\n')
            acc_iban = line.tr_bank_account_id.sanitized_acc_number
            if not acc_iban or len(acc_iban) > 35 or len(acc_iban) < 2:
                line_level_errors += _('Beneficiary IBAN is of incorrect format.\n')
            res_bank = line.tr_bank_account_id.bank_id
            if not res_bank.bic:
                line_level_errors += _('Beneficiary bank BIC is not found.\n')
            # Partner data constraints
            if partner.is_company and partner.country_id.code == 'LT' and not partner.kodas:
                line_level_errors += _('Beneficiary partner code is not specified.\n')

            # Raise the error if any of the lines have errors
            if line_level_errors:
                line_level_errors += _('\n\n Line - {}').format(line.tr_name)
                raise exceptions.ValidationError(line_level_errors)

            # Prepare global beneficiary block
            id_field = 'legal_code' if partner.is_company else 'personal_code'
            c_id_field = 'company_code' if partner.is_company else 'customer_code'

            # Build beneficiary block
            beneficiary_block = {
                'type': 'bank',
                'name': partner.display_name,
                'person_type': 'legal' if partner.is_company else 'natural',
                'additional_information': {
                    'type': 'legal' if partner.is_company else 'natural'
                },
                'bank_account': {
                    'iban': line.tr_bank_account_id.sanitized_acc_number,
                },
            }
            # Do not append the bic if receiver's bank is Paysera
            if res_bank.bic != abi.PAYSERA:
                beneficiary_block['bank_account']['bic'] = res_bank.bic

            # Check constraints and prepare purpose block
            purpose_field = 'reference' if line.tr_structured else 'details'
            purpose_value = line.tr_ref if line.tr_structured else line.tr_name or line.tr_ref or str()
            purpose_value = unidecode(purpose_value.decode('utf-8'))

            # Get the related rules for specific bank
            rules = pt.PAYMENT_INIT_FIELD_RULES_TO_BIC.get(res_bank.bic, [])
            for rule in rules:
                # Just this one for the moment
                if rule == 'address_rule':
                    if not partner.country_id.code or not partner.city:
                        raise exceptions.ValidationError(
                            _('Siunčiant mokėjimą į "{}" banką, partnerio kortelėje '
                              'privaloma nurodyti gavėjo šalį ir miestą.').format(res_bank.name)
                        )
                    # Update the beneficiary information with the city and country
                    address_line = unidecode(partner.city.decode('utf-8'))
                    beneficiary_block.update({
                        'address': {
                            'country_code': partner.country_id.code,
                            'address_line': address_line,
                        },
                    })
                    beneficiary_block['additional_information'].update({
                        'country': partner.country_id.code,
                        'city': address_line,
                    })
                # Used to check the length
                if rule == 'purpose_length_rule' and len(purpose_value) > pt.STATIC_PURPOSE_LENGTH:
                    raise exceptions.ValidationError(
                        _('Siunčiant mokėjimą į "{}" banką, mokėjimo paskirties/aprašymo laukelio turinys '
                          'negali būti ilgesnis nei {} simbolių.').format(res_bank.name, pt.STATIC_PURPOSE_LENGTH)
                    )

            # Update beneficiary field
            if partner.kodas:
                beneficiary_block.update({
                    'identifiers': {id_field: partner.kodas},
                    'client_identifier': {c_id_field: partner.kodas}
                })
            # Update purpose block
            purpose_block = {purpose_field: purpose_value}

            # Prepare transaction data
            transaction_api_data = {
                'amount': amount_block,
                'beneficiary': beneficiary_block,
                'payer': payer_block,
                'urgency': urgency,
                'purpose': purpose_block,
            }

            # Call the endpoint to post the transfer
            # (It's not visible in front-end at this point)
            successful_call, response_data = self.call(
                action='post_transfer',
                extra_data=transaction_api_data,
                forced_client_id=forced_client_id,
                forced_mac_key=forced_mac_key
            )

            # Prepare base values
            message_to_post = _('Payment export to Paysera was accepted')
            error_template = _('Payment export to Paysera was rejected. Error message - {}')
            export_state = 'rejected'
            line_vals = {}

            # If call to post the transfer was successful,
            # try to register the transfer so it's visible in front-end
            if successful_call:
                object_id = response_data['id']
                successful_call, response_data = self.call(
                    action='register_transfer',
                    extra_data={'object_id': object_id},
                    forced_client_id=forced_client_id,
                    forced_mac_key=forced_mac_key
                )
                if successful_call:
                    line_vals.update({'api_external_id': object_id})
                    export_state = 'accepted_partial' if line.partial_payment else 'accepted'
                else:
                    message_to_post = error_template.format(response_data['error'])
            else:
                message_to_post = error_template.format(response_data['error'])

            # Write base values to the export jobs
            line_vals.update({
                'export_state': export_state,
                'last_error_message': message_to_post,
                'system_notification': response_data['system_notification']
            })
            line.sudo().write(line_vals)
            line.post_message_to_related(message_to_post)

        # Initiate payment transfer wizard, which displays the statuses of
        # just-exported statements. Signing is available at this step (If it's enabled)
        transfer_wizard = self.env['paysera.payment.transfer.wizard'].create({
            'bank_export_job_ids': [(4, x.id) for x in batch_exports]
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'paysera.payment.transfer.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'res_id': transfer_wizard.id,
            'view_id': self.env.ref('sepa.form_paysera_payment_transfer_wizard').id,
        }

    # Statement import-from-bank methods ------------------------------------------------------------------------------

    @api.model
    def api_fetch_transactions_prep(self, journal, date_from, date_to, fetch_job):
        """
        Method that prepares transaction fetching for specific
        Paysera journal - creates separate thread which calls statement
        fetching. Called manually
        :param journal: account.journal record
        :param date_from: date_from (str)
        :param date_to: date_to (str)
        :param fetch_job: Statement fetch job record
        :return: result of query_statements()
        """
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
            journal = env['account.journal'].browse(journal_id)
            fetch_job = env['bank.statement.fetch.job'].browse(fetch_job_id)
            fetching_state, error_message = 'succeeded', str()
            try:
                # Try to push the statements
                env['paysera.api.base'].api_fetch_transactions(journal, date_from, date_to, manual_action=True)
            except Exception as exc:
                new_cr.rollback()
                fetching_state = 'failed'
                error_message = _('Išrašų traukimo klaida - {}').format(exc.args[0] if exc.args else str())

            fetch_job.close_statement_fetch_job(fetching_state, error_message)
            # Commit the changes and close the cursor
            new_cr.commit()
            new_cr.close()

    @api.model
    def api_fetch_transactions(self, journal=None, date_from=None, date_to=None, manual_action=False):
        """
        Method that calls recursive method to fetch bank statements for each
        active and correctly configured Paysera wallet using
        given period of date_from and date_to. If date_to is not specified
        current time is used instead.
        :param date_from: Period date from
        :param date_to: Period date to
        :param journal: account.journal record (optional, if not provided, transactions
            are fetched for every Paysera journal in the system)
        :param manual_action: Indicates whether the action is manual or system (cron)
        function is called recursively again.
        :return: None
        """

        # Check whether API is correctly configured
        if not self.check_configuration():
            return

        # Assign the date from if it's not passed
        if not date_from:
            date_from = (datetime.now() - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        filter_currency = False
        journal = self.env['account.journal'] if journal is None else journal
        action = 'wallet_statements_manual' if manual_action else 'wallet_statements'

        # If journal is provided try to find the specific wallet,
        # otherwise execute method for all of the following wallets
        if journal:
            # On single journal, we filter out entries only for that currency
            # since one wallet can have multiple IBANs with different currencies
            filter_currency = journal.currency_id.name or self.env.user.company_id.currency_id.name
            wallets = self.env['paysera.wallet'].get_related_wallet(journal)
        else:
            # Get wallets, loop through them and call the endpoint
            wallets = self.env['paysera.wallet'].get_wallets(fully_functional=True)

        # Loop through wallets, and fetch transactions for the period
        for wallet in wallets:
            transactions = self.api_fetch_transactions_recursive(action, wallet, date_from, date_to)
            if transactions:
                self.process_transactions(transactions, wallet, filter_currency)

    @api.model
    def api_fetch_transactions_recursive(self, action, wallet, date_from, date_to, depth=3):
        """
        Recursive part of 'api_fetch_transactions' split into separate method
        so 'process_transactions' can be called on the whole batch, reducing
        the chance of concurrency while updating the wallets.
        If too much data is received, split the period, and recursively
        call the method again.
        :param action: Paysera API action (str)
        :param wallet: paysera.wallet record for which transactions are fetched (record)
        :param date_from: period date from (str)
        :param date_to: period date to (str)
        :param depth: period split depth parameter, 3=day, 2=hour, 1=10minutes (int)
        :return: fetched transactions (list)
        """
        def convert_dates(date_str):
            """Convert date string to datetime object"""
            try:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
            return date_dt

        # Convert dates
        date_to_dt = convert_dates(date_to) if date_to else datetime.now()
        date_from_dt = convert_dates(date_from)

        full_transaction_set = []
        successful_call, response_data = self.call(
            action=action,
            extra_data={'object_id': wallet.wallet_id,
                        'limit': pt.API_RECORD_LIMIT,
                        'd_from': date_from_dt.strftime('%s'),
                        'd_to': date_to_dt.strftime('%s'),
                        },
        )
        if successful_call:
            transactions = response_data.get('statements', [])
            # Max limit of the transactions returned is 200
            # if we get more than that, request is potentially throttled
            # and we try to go day by day
            if len(transactions) == pt.API_RECORD_LIMIT:
                temp_date_dt = date_to_dt
                if depth:
                    # Divide period based on level:
                    #   - First level: By day
                    #   - Second level: By hour
                    #   - Third level: By 10 minutes
                    period = API_THROTTLING_PERIOD_SPLIT.get(depth)
                    while temp_date_dt > date_from_dt:
                        date_to = temp_date_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        date_from = (temp_date_dt - relativedelta(**period)).strftime(
                            tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        full_transaction_set.extend(
                            self.api_fetch_transactions_recursive(action, wallet, date_from, date_to, depth - 1)
                        )
                        temp_date_dt -= relativedelta(**period)
                else:
                    # TODO: IF TRANSACTIONS OVERFLOW 200/10Min EXTEND THIS PART
                    raise exceptions.ValidationError(_('Paysera API overflow: Received too many transactions'))
            else:
                return transactions
        else:
            wallet.write({'state': 'configuration_error', 'error': response_data.get('error', str())})
        return full_transaction_set

    @api.model
    def process_transactions(self, transactions, wallet, filter_currency=False):
        """
        Method used to process transactions that were received by an API response.
        Transactions are grouped by a date to a format that corresponds
        to account.bank.statement.line structure. Grouped transactions
        are passed to bank statement creation method.
        :param transactions: list-of-transaction dicts received via API
        :param wallet: paysera.wallet record that lines belong to
        :param filter_currency: If set, indicates whether only specific currency should be processed
        :return: None
        """
        transactions_by_journal = {}
        company_currency = self.sudo().env.user.company_id.currency_id
        earliest_date = datetime.now()

        journals_dict = {}
        for wallet_iban in wallet.paysera_wallet_iban_ids:
            journals_dict[wallet_iban.currency_id.name or company_currency.name] = wallet_iban.journal_id

        # Define transaction type to default name mapping
        transaction_type_to_name = {
            'transfer': '/',
            'commission': _('Commissions'),
            'cash': _('Cash Operations'),
            'currency': _('Currency exchange'),
            'tax': _('Tax operations'),
            'return': _('Refund'),
            'automatic_payment': _('Automatic payment'),
            'card_transaction': _('Card payment')
        }

        for transaction in transactions:
            # Get currency code of the transaction
            currency_code = transaction.get('currency', 'EUR')
            if filter_currency and currency_code != filter_currency:
                continue

            # Paysera returns historic currencies that are not used anymore
            # like 'LTL' or artificial currencies like eCoins/gold.
            # If we receive either of those currencies we just skip
            if not self.env['res.currency'].search_count([('name', '=', currency_code)]):
                continue

            journal = journals_dict.get(currency_code)
            if not journal:
                # TODO: This part might be improved in the future,
                # TODO: now it's messy due to weird object relationship in Paysera system:
                # One account can have multiple IBANs (they are passed as a list), however IBAN is not included
                # in the response of transaction list, thus it's not clear which IBANs' transactions are fetched.
                # Their support told us that for now this list is not going to contain more than one IBAN, but it
                # might in the future when they update their API... So this part is going to be updated as well,
                # based on their changed response structure.
                body = 'Received statement with currency %s. ' \
                       'However there is no Paysera wallet with this currency in the system' % currency_code
                self.env['script'].send_email(
                    ['support@robolabs.lt'],
                    'Paysera API: Received unexpected statement. DB: [%s] ' % self.env.cr.dbname, body
                )
                continue

            # Get both of transaction IDs
            transaction_id = transaction.get('id')
            transfer_id = transaction.get('transfer_id')

            # Get transaction timestamp, datetime, and date
            tr_ts = datetime.utcfromtimestamp(transaction.get('date'))
            offset = int(pytz.timezone('Europe/Vilnius').localize(tr_ts).strftime('%z')[1:3])
            tr_ts_local = tr_ts + relativedelta(hours=offset)

            if tr_ts_local < earliest_date:
                earliest_date = tr_ts_local

            tr_date = tr_ts_local.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            # Get the amount which is represented in non-decimal (no floating point)
            tr_amount = transaction.get('amount', 0)
            # P3:DivOK
            tr_amount = tr_amount / 100 if isinstance(tr_amount, (float, int)) else 0
            # Always convert to float, so division is correct

            # Convert amount based on a direction
            tr_amount *= -1 if transaction.get('direction', 'out') == 'out' else 1

            # Check whether the line already exists in the system using date, amount and IDs
            duplicate_line = self.env['account.bank.statement.line'].search(
                ['|', ('entry_reference', '=', transaction_id),
                 ('entry_reference', '=', transfer_id),
                 ('statement_id.sepa_imported', '=', True),
                 ('journal_id', '=', journal.id),
                 ('date', '=', tr_date)]
            )
            # Use filtered with float_compare for correct results
            if duplicate_line.filtered(lambda x: not tools.float_compare(x.amount, tr_amount, precision_digits=2)):
                continue

            # Set default
            transactions_by_journal.setdefault(journal, {})
            transactions_by_journal[journal].setdefault(tr_date, [])

            # Get reference and details of the transaction
            transaction_type = transaction.get('type', 'transfer')
            default_name = transaction_type_to_name.get(transaction_type, '/')

            n_details = transaction.get('details', default_name)
            reference = transaction.get('reference_number', '/')

            # Get other party info from transaction
            partner_info = transaction.get('other_party', {})
            partner_name = partner_info.get('display_name', str())
            partner_iban = partner_info.get('account_number', str())
            partner_code = partner_info.get('code', str())

            part_identification = ('kodas', partner_code) if partner_code else None

            partner_id = self.env['account.sepa.import'].get_partner_id(
                partner_name=partner_name,
                partner_iban=partner_iban,
                partner_identification=part_identification
            )
            values = {
                'journal_id': journal.id,
                'amount': tr_amount,
                'name': n_details or '/',
                'ref': reference or '/',
                'date': tr_date,
                'entry_reference': transaction_id,
                'info_type': 'unstructured',
                'imported_partner_name': partner_name,
                'imported_partner_iban': partner_iban,
                'imported_partner_code': partner_code,
                'partner_id': partner_id,

            }
            transactions_by_journal[journal][tr_date].append(values)

        # After transactions are grouped, call bank statement creation
        self.create_bank_statements(transactions_by_journal, earliest_date)

    @api.model
    def create_bank_statements(self, processed_transactions, earliest_date):
        """
        Method that creates account.bank.statement records from passed bulk
        of grouped and processed transactions that were received via API.
        Earliest date is used to fetch the end balance from the statement before
        this day (used as starting balance for statements-to-be created)
        :param processed_transactions: {res.journal: {'2020-01-01': [{TR1_DATA}, {TR2_DATA}]...}} (dict)
        :param earliest_date: earliest date of the transaction bulk
        :return: None
        """
        statements = self.env['account.bank.statement']
        journals = self.env['account.journal']
        before_batch_statements_by_journal = {}

        for journal, transactions_by_day in iteritems(processed_transactions):
            base_domain = [
                ('journal_id', '=', journal.id),
                ('sepa_imported', '=', True),
                ('partial_statement', '=', False),
            ]
            # Check whether there is a statement day earlier than earliest date of this bulk
            # if it does exist, use it's end balance for further calculations
            before_batch_statement = self.env['account.bank.statement'].search(
                base_domain + [('date', '<', earliest_date)], limit=1, order='date desc, create_date desc')

            # Add before batch statement to mapping dict
            before_batch_statements_by_journal[journal] = before_batch_statement

            # If latest statement exits, and it's not a partial statement, we take it's end balance
            balance_end_compute = 0.0
            if before_batch_statement:
                balance_end_compute = before_batch_statement.balance_end_real

            # Loop through the list of dates, and check whether new statement should be created
            # or already existing statement should be updated with newly fetched lines

            sorted_transactions = sorted(transactions_by_day.items(), key=lambda k: k[0])
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
                    })
                statements |= statement
            journals |= journal

        # Update the end balances of all journals, and force the end balance to the latest statement
        # Because in this API we do not get the balance for specific date on statement call
        date_today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for journal in journals:
            balance_end = journal.api_end_balance
            journal_currency = journal.currency_id.name or 'EUR'
            before_statement = before_batch_statements_by_journal.get(journal)

            # Try to normalize the statements in ascending way, if it fails (no initial starting entry),
            # execute the current day's balance fetching and normalize them in descending way
            normalized_ascending = self.env['account.bank.statement'].normalize_balances_ascending(
                journal_ids=journal.ids, force_normalization=False)
            if not normalized_ascending:
                # Search for today's statement, since we can only fetch Paysera balance
                # for current moment, we only update today's statement.
                latest_statement = self.env['account.bank.statement'].search(
                    [('sepa_imported', '=', True),
                     ('partial_statement', '=', False),
                     ('journal_id', '=', journal.id),
                     ('date', '=', date_today)],
                    order='date desc, create_date desc', limit=1)
                if latest_statement and not before_statement:
                    # Get related wallet and wallet IBAN records
                    wallet_iban = self.env['paysera.wallet.iban'].search(
                        [('journal_id', '=', journal.id)])
                    related_wallet = wallet_iban.paysera_wallet_id

                    if related_wallet:
                        # Call endpoint for specific wallet with this specific structure
                        # without updating the actual wallets to prevent concurrency
                        successful_call, response_data = self.call(
                            action='wallet_balance',
                            extra_data={
                                'object_id': related_wallet.wallet_id,
                                'manual_action': False
                            },
                        )
                        if successful_call:
                            # Fetch the balance for this particular journal
                            # response structure is based on currency
                            end_balance_data = response_data.get(journal_currency, {})
                            if end_balance_data:
                                # P3:DivOK -- First value is converted to fload, because it's passed as
                                # a string, so float conversion needs to be kept
                                balance_end = tools.float_round(
                                    float(end_balance_data.get('at_disposal', 0)) / 100, precision_digits=2)
                    latest_statement.write({'balance_end_real': balance_end, 'balance_end_factual': balance_end})

                # Normalize balances of bank statements
                empty_statements = self.env['account.bank.statement'].normalize_balances_descending(
                    journal_ids=journal.ids
                )
                statements |= empty_statements

        # Check whether lines should be reconciled with GPM lines
        lines_to_skip = self.env['account.bank.statement.line']
        if not self.env.context.get('skip_autoreconciliation_sodra_gpm'):
            lines_to_skip = statements._auto_reconcile_SODRA_and_GPM()

        # Try to apply import rules and auto reconcile the lines with other accounting entries
        lines_to_skip += statements.with_context(skip_error_on_import_rule=True).apply_journal_import_rules()
        statements.mapped('line_ids').auto_reconcile_with_accounting_entries(lines_to_skip=lines_to_skip)

    # Other API methods -----------------------------------------------------------------------------------------------

    @api.model
    def api_check_live_transaction_state(self, bank_export):
        """
        Method that is used to check live transaction state
        for give bank.export.job record.
        :param bank_export: bank.export.job object
        :return: None
        """
        if not self.check_configuration(fully_functional=False):
            return

        successful_call, response_data = self.env['paysera.api.base'].call(
            action='get_transfer',
            forced_mac_key=self.get_mac_key(endpoint_group='transfers'),
            forced_client_id=self.get_client_id(endpoint_group='transfers'),
            extra_data={'object_id': bank_export.api_external_id},
        )
        # if call is not successful, state in the system is not change
        if successful_call:

            # Map Paysera states to Robo bank states
            paysera_state_mapping = {
                'registered': 'accepted',
                'done': 'processed',
                'rejected': 'revoked',  # This is correct
                'revoked': 'revoked',
                'failed': 'rejected',  # This is correct
            }

            # Fetch and convert the state
            state = response_data.get('status')
            live_export_state = paysera_state_mapping.get(state)
            if live_export_state:

                # If payment is partial, get the partial state
                if bank_export.partial_payment:
                    live_export_state = self.env['api.bank.integrations'].convert_to_partial_state(live_export_state)

                # If states do not match, write the live state
                if bank_export.export_state != live_export_state:
                    bank_export.write({'export_state': live_export_state})

    @api.model
    def api_revoke_transaction(self, bank_export):
        """
        Method that is used to revoke specific transaction
        that was already sent to the bank.
        !FOR NOW ONLY USED IN SCRIPTS!
        :param bank_export: bank.export.job object
        :return: successful_call flag (bool), response_data (dict)
        """
        if not self.check_configuration(fully_functional=False):
            return
        successful_call, response_data = self.call(
            action='delete_transfer',
            forced_mac_key=self.get_mac_key(endpoint_group='transfers'),
            forced_client_id=self.get_client_id(endpoint_group='transfers'),
            extra_data={'object_id': bank_export.api_external_id},
        )
        return successful_call, response_data

    @api.model
    def api_fetch_wallet_balance(self, manual_action=False):
        """
        Method that is used to fetch balances for each wallet.
        :param manual_action: Identifies whether the action is manual or not
        :return: None
        """
        # Check whether API is correctly configured (non-fully functional)
        if not self.check_configuration(fully_functional=False):
            return

        # Determine whether action is manual or not
        action = 'wallet_balance_manual' if manual_action else 'wallet_balance'

        # Get wallets, loop through them and call the endpoint
        active_wallets = self.env['paysera.wallet'].get_wallets()
        for wallet in active_wallets:
            successful_call, response_data = self.call(
                action=action,
                extra_data={'object_id': wallet.wallet_id, 'manual_action': manual_action},
            )
            # If call is not successful, deactivate the wallet
            # otherwise fetch balances and pass them to distributor
            if successful_call:
                grouped_data = {}
                for currency_code, values in iteritems(response_data):
                    # Paysera still sometimes passes historic currencies that are not used anymore
                    # like 'LTL'. If we receive either of those currencies we just skip
                    currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
                    if not currency:
                        continue

                    # P3:DivOK -- First values are converted to fload, because they are
                    # passed as a string, so float conversion needs to be kept
                    end_balance = tools.float_round(float(values.get('at_disposal', 0)) / 100, precision_digits=2)
                    reserved_amount = tools.float_round(float(values.get('reserved', 0)) / 100, precision_digits=2)

                    # Group data by currency
                    grouped_data[currency] = {
                        'end_balance': end_balance,
                        'reserved_amount': reserved_amount
                    }
                wallet.distribute_end_balances(grouped_data)
            else:
                # Stop the process on external failure flag
                # for now, only on this method.
                if response_data.get('external_failure'):
                    return
                wallet.write({'state': 'configuration_error', 'error': response_data.get('error', str())})

    @api.model
    def api_initiate_wallets(self, raise_exception=False):
        """
        Method that is used to initiate Paysera wallets.
            - Fetch wallet data
            - Create corresponding objects
            - Fetch balances for the related wallets
        :param raise_exception: Identifies whether action is manual or not
        should be raised or not
        :return: None
        """
        # Check whether API is correctly configured (non-fully functional)
        if not self.check_configuration(fully_functional=False, init=True):
            return

        conf_obj = self.get_configuration()

        # If there is no user ID call with access tokens
        c_paysera_uid = conf_obj.paysera_user_id
        if not c_paysera_uid:
            u_successful_call, u_response_data = self.call(
                action='user',
                forced_client_id=conf_obj.access_token,
                forced_mac_key=conf_obj.access_token_mac_key
            )
        else:
            u_successful_call, u_response_data = self.call(
                action='user_id',
                extra_data={'object_id': c_paysera_uid},
            )

        if u_successful_call:
            # Get various information about user that authenticated the access to wallets
            wallet_ids = u_response_data.get('wallets', [])
            full_u_name = u_response_data.get('display_name')
            identity_block = u_response_data.get('identity', {})
            paysera_user_id = u_response_data.get('id', 0)

            # If identity block is not reachable, raise an error
            if not identity_block:
                if not raise_exception:
                    return
                raise exceptions.ValidationError(
                    _('Action cannot be performed - access to this Paysera account has not been granted.'))
            u_code = identity_block.get('code')
            if not c_paysera_uid or paysera_user_id != c_paysera_uid:
                conf_obj.write({'paysera_user_id': paysera_user_id})
                self.env.cr.commit()

            # Loop through the wallets of the user
            # And call the wallet endpoint for each ID
            for wallet_id in wallet_ids:
                # Search for the wallet in the system
                wallet = self.env['paysera.wallet'].search([('wallet_id', '=', wallet_id)])
                # If wallet is disabled, continue
                if wallet and not wallet.activated:
                    continue

                successful_call, response_data = self.call(
                    action='wallet',
                    extra_data={'object_id': wallet_id},
                )

                # Prepare dummy values
                wallet_values = {'state': 'configuration_error', 'error_message': response_data.get('error', str())}
                active = False

                # 1. Call to get the wallet info
                if successful_call:
                    # Fetch base wallet data
                    wallet_data = response_data.get('account', {})

                    # Initialize other wallet variables
                    iban_list = wallet_data.get('ibans', [])
                    active = wallet_data.get('status') == 'active'
                    user_type = wallet_data.get('owner_type')
                    paysera_account_number = wallet_data.get('number')

                    # Prepare the wallet values
                    wallet_values.update({
                        'paysera_configuration_id': conf_obj.id,
                        'paysera_account_number': paysera_account_number,
                        'iban_account_number': iban_list and iban_list[0] or str(),
                        'wallet_id': wallet_id,
                        'user_type': user_type,
                        'user_name': full_u_name,
                        'user_code': u_code
                    })

                    # If First call is successful, try to check the further rights
                    # 2. Dummy call to the wallet statements
                    successful_call, response_data = self.call(
                        action='wallet_statements_manual',
                        extra_data={'object_id': wallet_id,
                                    'limit': pt.API_RECORD_LIMIT,
                                    'd_from': datetime.utcnow().strftime('%s'),
                                    'd_to': datetime.utcnow().strftime('%s'),
                                    },
                    )
                    # If second call is successful - state is configured
                    if successful_call:
                        wallet_values['state'] = 'configured'
                    else:
                        # Fetch the second error message if any
                        error_message = response_data.get('error', str())
                        if error_message:
                            wallet_values['error_message'] = error_message

                # If wallet does not exist in the system and it's active
                # Create it, otherwise write those values, and commit
                if not wallet and active:
                    self.env['paysera.wallet'].create(wallet_values)
                else:
                    wallet.write(wallet_values)
                self.env.cr.commit()

        elif raise_exception:
            raise exceptions.ValidationError(
                _('Failed to access Paysera wallets. Repeat this action and contact administrators if it fails again'))

        # Fetch the balance for the wallets
        self.api_fetch_wallet_balance(manual_action=True)

    # -----------------------------------------------------------------------------------------------------------------
    # Core API Methods ------------------------------------------------------------------------------------------------

    @api.model
    def call(self, action, extra_data=None, forced_client_id=None, forced_mac_key=None, retries=0):
        """
        Main method used to prepare data/structures for Paysera API call.
        :return: True/False (based on success of the call), response_data
        """
        api_data = self.get_api_endpoint_data(action, extra_data=extra_data)
        response = self.call_api_endpoint(
            api_data, forced_client_id=forced_client_id, forced_mac_key=forced_mac_key)
        response_data, status_code = self.sanitize_response(action, response, retries)

        if status_code == pt.RENEW_CODE:
            # If response was to renew the code, refresh tokens, and try again
            return self.call(action, extra_data, forced_client_id, forced_mac_key, retries + 1)

        if status_code == pt.REFRESH_RENEW_CODE:
            self.post_expired_key_warning()

        # Check whether call was successful
        successful_call = status_code == 200
        return successful_call, response_data

    @api.model
    def call_api_endpoint(self, api_data, forced_client_id=None, forced_mac_key=None):
        """
        Method used to generate authentication key and call specific Paysera API endpoint.
        Each call has separate authentication key which is composite hash
        of following values:
            - Timestamp
            - Nonce
            - Request method (GET/POST..)
            - Endpoint
            - Host
            - Port
        After authentication specific endpoint is called, returned data is
        extracted, sanitized and returned
        :param api_data: dict {request_endpoint, request_method, request_url, data, data_type}
        :param forced_client_id: forced client ID (used for API testing)
        :param forced_mac_key: forced mac key (used for API testing)
        :return: response of specific API endpoint (object)
        """

        req_method = api_data['request_method']

        # Get client ID and mac key
        client_id = str(forced_client_id or self.get_client_id())
        mac_key = str(forced_mac_key or self.get_mac_key())

        # Init timestamp and nonce
        timestamp = str(time.time())

        chars = string.ascii_lowercase + string.digits + string.ascii_uppercase
        nonce = str().join(random.choice(chars) for _ in range(pt.STATIC_NONCE_SIZE))

        # Get data type
        json_data = api_data.get('json_data')
        extra_data = encoded_data = str()
        if req_method == 'POST':
            # Make ordered dict of the data
            if json_data:
                encoded_data = json.dumps(api_data['data'])
            else:
                data = OrderedDict([(k, str(v)) for k, v in iteritems(api_data['data'])])
                encoded_data = urllib.urlencode(data)
            # Calculate the hash of the data
            data_hash = str(base64.b64encode(hashlib.sha256(encoded_data).digest()).decode())
            encoded_data_hash = urllib.quote_plus(data_hash)
            extra_data = 'body_hash={}'.format(encoded_data_hash)

        # Format H-MAC message body
        message = '{}\n{}\n{}\n{}\n{}\n{}\n{}\n'.format(
            timestamp, nonce, api_data['request_method'],
            api_data['request_endpoint'], pt.STATIC_PAYSERA_HOST, pt.STATIC_PAYSERA_PORT, extra_data)

        # Generate H-MAC hash string and decode it
        mac_object = hmac.new(
            mac_key,
            msg=message,
            digestmod=hashlib.sha256
        )
        mac_value = base64.b64encode(mac_object.digest()).decode()
        auth_header = 'MAC id="{}", ts="{}", nonce="{}", mac="{}"'.format(client_id, timestamp, nonce, mac_value)

        # Determine content type
        content_type = 'application/x-www-form-urlencoded;charset=utf-8'
        if json_data:
            content_type = 'application/json;charset=utf-8'

        if req_method == 'POST':
            auth_header += ', ext="{}"'.format(extra_data)
            response = requests.post(
                api_data['request_url'], headers={
                    'Authorization': auth_header,
                    'Content-type': content_type
                }, data=encoded_data)
        elif req_method == 'PUT':
            # PUT requests to Paysera do not contain any data (thus far with what we integrated)
            response = requests.put(api_data['request_url'], headers={'Authorization': auth_header})
        elif req_method == 'DELETE':
            # PUT requests to Paysera do not contain any data (thus far with what we integrated)
            response = requests.delete(api_data['request_url'], headers={'Authorization': auth_header})
        # Call the endpoint and load it's response
        else:
            response = requests.get(api_data['request_url'], headers={'Authorization': auth_header})
        return response

    @api.model
    def get_api_endpoint_data(self, action, extra_data=None):
        """
        Prepare specific Paysera API endpoint based on passed action value
        :param action - api endpoint in scoro system
        :param extra_data - extra parameters that are passed to the endpoint
        :return formatted message
        """

        extra_data = {} if extra_data is None else extra_data

        # Paysera endpoint url that is
        # mapped to action in our system
        endpoint_mapping = {
            'user': '/rest/v1/user/me',
            'user_id': '/rest/v1/user/{object_id}',
            'test_api': '/transfer/rest/v1/transfers/{object_id}/register',
            'fetch_tokens': '/oauth/v1/token',
            'wallet': '/rest/v1/wallet/{object_id}',
            'wallet_balance': '/rest/v1/wallet/{object_id}/balance?show_historical_currencies=true',
            'wallet_balance_manual': '/rest/v1/wallet/{object_id}/balance?show_historical_currencies=true',
            'wallet_balance_converted': '/rest/v1/wallet/{object_id}/balance?convert_to={currency_code}',
            'wallet_statements': '/rest/v1/wallet/{object_id}/statements?from={d_from}&to={d_to}&limit={limit}',
            'wallet_statements_manual': '/rest/v1/wallet/{object_id}/statements?from={d_from}&to={d_to}&limit={limit}',
            'post_transfer': '/transfer/rest/v1/transfers',
            'get_transfer': '/transfer/rest/v1/transfers/{object_id}',
            'delete_transfer': '/transfer/rest/v1/transfers/{object_id}',
            'register_transfer': '/transfer/rest/v1/transfers/{object_id}/register',
            'sign_transfer': '/transfer/rest/v1/transfers/{object_id}/sign'
        }

        # Paysera method (GET, POST, PUT)
        # based on action in our system
        method_mapping = {
            'user': 'GET',
            'user_id': 'GET',
            'test_api': 'PUT',
            'wallet': 'GET',
            'wallet_balance': 'GET',
            'wallet_balance_manual': 'GET',
            'wallet_balance_converted': 'GET',
            'wallet_statements': 'GET',
            'wallet_statements_manual': 'GET',
            'fetch_tokens': 'POST',
            'post_transfer': 'POST',
            'get_transfer': 'GET',
            'register_transfer': 'PUT',
            'sign_transfer': 'PUT',
            'delete_transfer': 'DELETE',
        }

        # Indicates what actions expect JSON data
        json_actions = ['post_transfer']

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
        req_url = 'https://{}{}'.format(pt.STATIC_PAYSERA_HOST, endpoint)
        return {
            'request_url': req_url,
            'request_endpoint': endpoint,
            'request_method': method,
            'data': extra_data,
            'json_data': json_data
        }

    @api.model
    def sanitize_response(self, action, response, retries):
        """
        Sanitize the response of specific Paysera API endpoint
        :param action: API action
        :param response: response object
        :param retries: Number of retry calls for the same endpoint
        :return: response content (dict), status code (int)
        """
        status_code_mapping = {
            400: _('Incorrect passed data or expired API token.'),
            401: _('Invalid Paysera API keys.'),
            403: _('Access to the selected resource is forbidden.'),
            404: _('Specified object was not found in Paysera system.'),
            500: _('Error on Paysera server side, try again later.'),
        }

        # Determine if action is manual
        manual_action = action in pt.MANUAL_API_ACTIONS

        # Parse the JSON and get status code
        try:
            response_content = json.loads(response.content)
            status_code = response.status_code
        except (ValueError, AttributeError):
            response_content = {}
            status_code = 500

        description = response_content.get('error_description', str())
        error_base = response_content.get('error', str())
        # Always post fully unaltered system notification
        system_notification = '{} / {}'.format(description, error_base)

        # If status code is not 200, raise an error (or send a bug)
        if status_code != 200:
            # Compose an error message
            error_str = 'Paysera API error: {}.\n Description: {}.\n Status code - [{}]'.format(
                error_base,
                description,
                status_code
            )
            # Always log the exception
            _logger.info(error_str)

            if pt.RENEW_MESSAGE in description and status_code == 400 and retries < pt.API_RETRY_THRESHOLD:
                # If token is expired, force our renew static code
                self.cron_refresh_access_tokens()
                status_code = pt.RENEW_CODE

            elif pt.REFRESH_RENEW_MESSAGE in description and status_code == 400 and retries < pt.API_RETRY_THRESHOLD:
                # If token is expired, force our refresh renew static code
                status_code = pt.REFRESH_RENEW_CODE

            elif manual_action:
                # Test API is specific case, we use simulated wallet ID (because we do not have any
                # real wallet IDs at this point) to check whether the error is because of the keys
                # or because the wallet was not found. If wallet was not found it means, keys are correct
                # thus we return 200 response instead of 404
                if status_code == 404 and action == 'test_api':
                    response_content = {}
                    status_code = 200
                else:
                    if pt.ACCESS_ERROR in description:
                        status_code = 403
                    # If action is manual, override response content with user-friendly output
                    response_content = {
                        'error': _('API Call failed: {}').format(
                            status_code_mapping.get(status_code, _('Unexpected error')))
                    }
            # Add external failure flag on 500 server error
            # only after manual action check.
            elif status_code == 500:
                response_content['external_failure'] = True
            else:
                raise exceptions.ValidationError(error_str)
        # Always attach detailed admin error to the response
        response_content['system_notification'] = system_notification
        return response_content, status_code

    # -----------------------------------------------------------------------------------------------------------------
    # Cron Jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_refresh_access_tokens(self):
        """
        Cron job that is used to refresh access
        tokens if they are expired.
        :return: None
        """
        return
        # TODO: Disable this cron for now
        configuration = self.get_configuration(raise_exception=False)

        # If there's no configuration, or token is not present yet
        # there's nothing to refresh - return
        if not configuration.refresh_token:
            return

        # Call the endpoint to fetch token data
        successful_call, response_data = self.env['paysera.api.base'].call(
            action='fetch_tokens',
            extra_data={'refresh_token': configuration.refresh_token, 'grant_type': 'refresh_token'},
        )
        configuration.write_access_keys(successful_call, response_data, refresh=True)

    @api.model
    def cron_fetch_wallet_balance(self):
        """
        Cron that fetches end balances for each active wallet
        :return: None
        """
        # Don't run wallet balance fetching at night
        # some cron-jobs are delayed by the server load balancer
        # thus it has big possibility to intersect
        current_hour = datetime.now(pytz.timezone('Europe/Vilnius')).hour
        if current_hour > 7 or current_hour < 3:
            try:
                self.api_fetch_wallet_balance()
            except ConnectionError:
                # Do not spam on connection error, adding it to this cron is sufficient
                # enough, because only this one is called every 30min, others - once a day
                self.env.cr.rollback()

    @api.model
    def cron_fetch_statements_daily(self):
        """
        Cron that fetches daily bank statements for Paysera accounts
        :return: None
        """
        self.api_fetch_transactions()

    @api.model
    def cron_fetch_statements_weekly(self):
        """
        Cron that fetches weekly bank statements for Paysera accounts
        :return: None
        """
        date_from = (datetime.now() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.api_fetch_transactions(date_from=date_from)

    @api.model
    def cron_fetch_statements_monthly(self):
        """
        Cron that fetches monthly bank statements for Paysera accounts
        :return: None
        """
        return  # Todo: Disable monthly fetching cron for now
        date_from = (datetime.now() - relativedelta(day=1, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.api_fetch_transactions(date_from=date_from)

    # -----------------------------------------------------------------------------------------------------------------
    # Helper Methods --------------------------------------------------------------------------------------------------

    @api.model
    def post_expired_key_warning(self):
        """
        If token as well as refresh token are both expired,
        Post announcement to company CEO or user that configured Paysera
        to authenticate access once again
        :return: None
        """
        configuration = self.get_configuration()
        if configuration.expired_keys:
            return

        user = configuration.user_id or self.env.user.company_id.vadovas.user_id
        body = _('Rejected API key response was received from Paysera Bank - '
                 'Authorization of the access rights needs to be granted manually')
        msg = {
            'body': body,
            'subject': _('Request to renew Paysera access rights'),
            'priority': 'medium',
            'front_message': True,
            'rec_model': 'paysera.configuration',
            'rec_id': configuration.id,
            'partner_ids': user.partner_id.ids,
            'view_id': self.env.ref('sepa.form_paysera_configuration').id,
        }
        configuration.robo_message_post(**msg)
        configuration.write({'expired_keys': True})

    @api.model
    def get_client_id(self, endpoint_group='wallets'):
        """Return Paysera client ID value based on endpoint_group"""
        configuration = self.env['paysera.configuration'].search([])
        if endpoint_group == 'wallets':
            return configuration.sudo().paysera_api_client_id
        elif endpoint_group == 'transfers':
            return configuration.paysera_tr_api_client_id

    @api.model
    def get_mac_key(self, endpoint_group='wallets'):
        """Return Paysera token or base MAC key value"""
        configuration = self.env['paysera.configuration'].search([])
        if endpoint_group == 'wallets':
            return configuration.sudo().paysera_api_mac_key
        elif endpoint_group == 'transfers':
            return configuration.paysera_tr_api_mac_key

    @api.model
    def get_configuration(self, raise_exception=True):
        """Return Paysera MAC key value"""
        configuration = self.env['paysera.configuration'].search([])
        if not configuration and raise_exception:
            raise exceptions.ValidationError(_('Paysera configuration record was not found!'))
        return configuration

    @api.model
    def check_configuration(self, fully_functional=True, init=False):
        """
        Check whether Paysera integration is configured.
        If system has both keys set and at least one wallet configured,
        integration is working and method returns True, otherwise False
        :return: True/False
        """
        configuration = self.get_configuration(raise_exception=False)
        working = configuration.api_state == 'working' and configuration.initially_authenticated

        # Do not check for wallets on INIT, since we are fetching them here
        if init and working:
            return True

        wallets = self.env['paysera.wallet'].get_wallets(fully_functional=fully_functional)
        # Different criteria of configured API is evaluated based
        # on the endpoint group that is being called
        if working and wallets:
            return True

        return False


PayseraAPIBase()
