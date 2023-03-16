# -*- encoding: utf-8 -*-
import pytz
import paypalrestsdk
import werkzeug
import logging
from paypalrestsdk import exceptions as PayPalException
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)

PAYPAL_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S+0000'
PAYPAL_TRANSACTION_EVENT_CODES_MAPPER = {
    'T0000': 'General Payment',
    'T0001': 'Mass Pay Payment',
    'T0002': 'Subscription Payment',
    'T0006': 'Express Checkout Payment',
    'T0007': 'Website Payment',
    'T0011': 'Mobile Payment',
    'T0200': 'General Currency Conversion',
    'T0600': 'General Credit Card Withdrawal',
    'T0700': 'General Credit Card Deposit',
    'T1105': 'Reversal of General Account Hold',
    'T1106': 'Payment Reversal',
    'T1107': 'Payment Refund',
    'T1503': 'Hold on Available Balance',
    'T1900': 'General Account Correction',
}
PAYPAL_TRANSACTION_ENDPOINT = 'v1/reporting/transactions'
MAX_PAGE_SIZE = 500
class PaypalApiImport(models.TransientModel):
    _name = 'paypal.api.import'
    _description = 'Transient model that is used for bank statement import requests from PayPal using API solutions'

    def _default_date_to(self):
        offset = int(datetime.now(pytz.timezone(self._context.get('tz', 'Europe/Vilnius'))).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(days=1, hour=23, minute=59, second=59) - relativedelta(hours=offset)

    def _default_date_from(self):
        offset = int(datetime.now(pytz.timezone(self._context.get('tz', 'Europe/Vilnius'))).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(days=1) - relativedelta(day=1, hour=0, minute=0,
                                                                         second=0) - relativedelta(hours=offset)

    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    date_from = fields.Datetime(string='Data nuo', default=_default_date_from)
    date_to = fields.Datetime(string='Data iki', default=_default_date_to)
    apply_import_rules = fields.Boolean(string='Taikyti importavimo taisykles', default=True)

    @api.multi
    def query_statements_via_api(self, raise_if_no_transaction=True):
        """
        Query the Paypal API for transactions, and create account.bank.statement.lines accordingly
        :return: tree view of the created / updated statements, if any. Do nothing if none.
        :rtype: dict
        """
        self.ensure_one()
        journal = self.journal_id
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        transaction_currency = journal.currency_id.name or self.env.user.company_id.currency_id.name

        if (date_to_dt - date_from_dt).days > 30:  # TODO: check if it's hard limit or not
            raise exceptions.UserError(_(u'Skirtumas tarp datu negali buti didesnis nei 30 dienų'))
        if date_to_dt < date_from_dt:
            raise exceptions.UserError(_(u'Pabaigos data negali būti ankstesnė nei pradžios data'))

        try:
            api_client = paypalrestsdk.Api({
                'mode': 'sandbox' if journal.paypal_api_id.sandbox else 'live',
                'client_id': journal.paypal_api_id.client_id,
                'client_secret': journal.paypal_api_id.secret})
            fragment = {
                'start_date': date_from_dt.strftime(PAYPAL_DATETIME_FORMAT),
                'end_date': date_to_dt.strftime(PAYPAL_DATETIME_FORMAT),
                'fields': 'all',
                'transaction_status': 'S',  # TODO: should get also reversed / denied?
                'balance_affecting_records_only': 'Y',
                'transaction_currency': transaction_currency,
                'page_size': MAX_PAGE_SIZE
            }
            transactions = []
            page_number = 1
            total_pages = 1
            while page_number <= total_pages:
                fragment['page'] = page_number
                request_url = PAYPAL_TRANSACTION_ENDPOINT + '?' + werkzeug.url_encode(fragment)
                transactions_response = api_client.get(request_url)
                if 'error' in transactions_response.keys():
                    raise exceptions.UserError(transactions_response['error']['message'])
                transactions += transactions_response['transaction_details']
                if page_number == 1: #reset the total_pages from the 1st response
                    total_pages = int(transactions_response['total_pages'])
                page_number += 1
        except PayPalException.UnauthorizedAccess:
            raise exceptions.UserError(_(u'Netinkami prieigos raktai. Pakeisikte juos PayPal nustatymuose'))
        except PayPalException.ForbiddenAccess:
            raise exceptions.UserError(
                _(u'Neturite teisių importuoti tranzakcijas iš PayPal. Pakeisikte nustatymus PayPal platformoje'))
        except Exception as e:
            _logger.info('Failed Paypal API request: Error: %s', e)
            raise exceptions.UserError(_(u'Įvyko nenumatyta klaida importuojant tranzakcijas iš PayPal'))

        if not transactions and raise_if_no_transaction:
            raise exceptions.UserError(_(u'Šiame laikotarpyje nerasta jokių tranzakcijų'))
        elif not transactions:
            return {'type': 'ir.actions.do_nothing'}

        statements = self.process_transactions(transactions)
        if statements and self.apply_import_rules:
            statements.with_context(skip_error_on_import_rule=False).apply_journal_import_rules()

        if statements:
            # Get the latest statement for this journal
            statement = self.env['account.bank.statement'].search(
                [('journal_id', '=', journal.id)], order='date desc', limit=1)
            # Prepare balance date at, last second of latest statement day
            date_at = datetime.strptime(
                statement.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=23, minute=59, second=59)
            balance_data = self.env['paypal.api'].api_fetch_account_balance(
                journal=journal, date_at=date_at)
            if balance_data:
                try:
                    # If we fail to parse any part of the value, we just skip without updating
                    balance_amount = float(balance_data['balances'][0]['available_balance']['value'])
                except Exception as exc:
                    _logger.info('Paypal API: Failed to extract balance value: Error: %s', exc.args[0])
                else:
                    # Write the balance and normalize statements
                    statement.write({'balance_end_factual': balance_amount})
                    self.env['account.bank.statement'].normalize_balances_descending(journal_ids=journal.ids)

            action = self.env.ref('account.action_bank_statement_tree')
            return {
                'name': action.name,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': action.res_model,
                'domain': [('id', 'in', statements.ids)],
                'context': action.context,
                'type': 'ir.actions.act_window',
            }
        else:
            return {'type': 'ir.actions.do_nothing'}

    @api.multi
    def process_transactions(self, transactions):
        """
        Process transaction data as returned from the API, and create account.bank.statement.line if they don't already
        exist
        :param transactions: list of dictionaries containing data as returned by the Paypal API
        :return: created and/or updated account.bank.statement records
        :rtype: 'account.bank.statement' RecordSet
        """
        self.ensure_one()

        statements = self.env['account.bank.statement']
        journal = self.journal_id
        journal_currency = journal.currency_id or self.env.user.company_id.currency_id
        grouped_lines = {}
        for transaction in transactions:
            transaction_info = transaction['transaction_info']
            transaction_id = transaction_info['transaction_id']
            transaction_event_code = transaction_info.get('transaction_event_code')
            label = PAYPAL_TRANSACTION_EVENT_CODES_MAPPER.get(transaction_event_code)

            existing_statement_line = self.env['account.bank.statement.line'].search([
                ('entry_reference', '=', str(transaction_id)), ('journal_id', '=', self.journal_id.id)
            ], limit=1)
            if existing_statement_line:
                # Reset artificial statement status
                statement = existing_statement_line.statement_id
                if statement.artificial_statement:
                    statement.write({'artificial_statement': False, 'name': 'Paypal API import'})
                continue

            partner_name = partner_email = False
            try:
                payer_info = transaction['payer_info']
                partner_email = payer_info.get('email_address')
                payer_name = payer_info.get('payer_name', {})
                partner_name = payer_name.get('full_name') or payer_name.get('alternate_full_name')
                partner_id = self.env['sepa.csv.importer'].get_partner_id(partner_name=partner_name,
                                                                          partner_email=partner_email)
            except Exception as e:
                _logger.info('Paypal API: skipped partner detection for transaction #%s. Reason: %r', transaction_id, e)
                partner_id = False

            date = datetime.strptime(transaction_info['transaction_initiation_date'], PAYPAL_DATETIME_FORMAT).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)  # Or should we use updated_date?
            # TODO: date, check the timestamps, if UTC time or not, might require to read the timezone

            amount = transaction_info['transaction_amount']['value']
            currency = transaction_info['transaction_amount']['currency_code']
            if currency != journal_currency.name:
                _logger.info('Paypal API: currency mismatch, skipping transaction #%s', transaction_id)
                continue  # Should we raise or should we skip?
                # raise exceptions.UserError(_('Mokesčio valiuta skiriasi nuo žurnalo valiutos.'))
            new_vals = {
                'date': date,
                'journal_id': journal.id,
                'entry_reference': transaction_id,
                'partner_id': partner_id if partner_id else None,
                'info_type': 'unstructured',
                'name': label or '/',
                'ref': transaction_info.get('invoice_id'),
                'imported_partner_name': partner_name or partner_email,
                'amount': amount,
            }
            grouped_lines.setdefault(date, []).append(new_vals)
            if 'fee_amount' in transaction_info:
                fee_amount = transaction_info['fee_amount'].get('value', '0.0')
                fee_currency = transaction_info['fee_amount'].get('currency_code')
                if fee_currency != journal_currency.name:
                    raise exceptions.UserError(_('Mokesčio valiuta skiriasi nuo žurnalo valiutos.'))
                fee = str2float(fee_amount, '.')  # TODO: have it as a setting? Make sure it always is '.'
                has_fee = not tools.float_is_zero(fee, precision_rounding=journal_currency.rounding)
                if has_fee:
                    fee_vals = new_vals.copy()
                    fee_vals.update({
                        'is_fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': fee,
                    })
                    grouped_lines[date].append(fee_vals)

        for day in sorted(grouped_lines):
            line_vals = grouped_lines[day]
            statement = self._create_statement(line_vals)
            if statement:
                statements |= statement

        return statements

    @api.multi
    def _create_statement(self, lines):
        """
        Create (or update existing) account.bank.statement and populate with lines created from the provided values
        :param lines: a list of dictionaries of creation values for account.bank.statement.line records
        :return: the created or updated statement, or empty recordset
        :rtype: 'account.bank.statement' RecordSet
        """
        self.ensure_one()
        if lines:
            date = lines[0]['date']
            statement = self.env['account.bank.statement'].search([('journal_id', '=', self.journal_id.id),
                                                                   ('sepa_imported', '=', True),
                                                                   ('date', '=', date)], limit=1)
            if not statement:
                statement = self.env['account.bank.statement'].create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Paypal API import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})
            if statement.artificial_statement:
                statement.write({
                    'artificial_statement': False,
                    'name': 'Paypal API import',
                })

            statement.line_ids = [(0, 0, line) for line in lines if not line.get('is_fee')]
            fee_lines = [line for line in lines if line.get('is_fee')]
            for line in fee_lines:
                orig_line = self.env['account.bank.statement.line'].search([
                    ('entry_reference', '=', line['entry_reference']),
                    ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                for key in ['partner_id', 'imported_partner_name']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
        else:
            statement = self.env['account.bank.statement']
        return statement


PaypalApiImport()


def str2float(amount, decimal_separator):
    if not amount:
        return 0.0
    try:
        if decimal_separator == '.':
            return float(amount.replace(',', ''))
        else:
            return float(amount.replace('.', '').replace(',', '.'))
    except:
        return False
