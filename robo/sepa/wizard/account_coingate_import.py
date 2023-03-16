# -*- encoding: utf-8 -*-
from odoo.addons.queue_job.job import job
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import pytz
import re
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)


_input_fields = {
    'created at',
    'id', 'payout description', 'amount', 'currency', 'status', 'suma eur',
    'coingate order id', 'partneris', 'title', 'total amount', 'coingate fee amount', 'amount eur', 'fee eur',
    'receive currency', 'merchant order id',
}


class AccountCoinGateImport(models.TransientModel):

    _name = 'account.coingate.import'
    _inherit = 'sepa.csv.importer'

    @api.model
    def default_get(self, fields_list):
        res = super(AccountCoinGateImport, self).default_get(fields_list)
        if 'skip_bank_statement_normalization' in fields_list and 'journal_id' in res:
            journal = self.env['account.journal'].browse(res['journal_id'])
            res['skip_bank_statement_normalization'] = journal and journal.skip_bank_statement_normalization or False
        return res

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'coingate')]")
    skip_bank_statement_normalization = fields.Boolean(string='Praleisti banko išrašų normalizavimą')
    withdrawals = fields.Boolean(string='Withdrawal file')

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių CoinGate operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction_id'),
                             (_('Data'), 'created at'),
                             (_('Aprašymas'), 'title'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti CoinGate operacijų')

    def _preprocess_vals(self, vals):
        #Not calling ensure one, but this is wizard
        date_utc = vals.get('created at')
        if not date_utc:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        if 'utc' in date_utc.lower():
            date = date_utc.lower().replace('utc', '').strip()
            try:
                date = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                vals['reason'] = _('Neteisingas datos formatas.')
                return False
            user_tz = pytz.timezone(self.env.context.get('tz') or 'Europe/Vilnius')
            date = user_tz.fromutc(date).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            date = datetime.strptime(date_utc, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        vals['date'] = date
        if self.withdrawals:
            transaction_id = vals.get('id')
            if not transaction_id:
                vals['reason'] = _('id lauko nėra')
                return False
            vals['transaction_id'] = transaction_id
            status = vals.get('status', 'completed')
            if status.lower() != 'completed':
                vals['reason'] = _("Būsena yra ne 'available' (%s)") % status
                return False
        else:
            transaction_id = vals.get('coingate order id')
            if not transaction_id:
                vals['reason'] = _('CoinGate Order ID lauko nėra')
                return False
            vals['transaction_id'] = transaction_id
            for i in ['total amount', 'coingate fee amount', 'amount eur', 'fee eur']:
                if i not in vals:
                    vals['reason'] = 'Missing %s field' % i
                    return False
        return True

    @job
    def _process_lines(self, vals):
        self.ensure_one()
        if self.withdrawals:
            return self._process_lines_withdrawals(vals)
        statement_ids = []
        AccountBankStatementLine = self.env['account.bank.statement.line']

        journal_currency = self.journal_id.currency_id or self.env.user.company_id.currency_id
        ccurrency = self.env.user.company_id.currency_id
        date_format = self.force_date_format or self._guess_date_format(vals)
        datetimes = {}
        for day in vals:
            try:
                date = datetime.strptime(day, date_format)
            except ValueError:  # if there was a forced format, it was not checked
                raise exceptions.UserError(_('Neteisingas datos formatas.'))
            datetimes[day] = date

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')
                currency_code = line_vals.get('receive currency')
                if currency_code is not None and currency_code.upper() != journal_currency.name:
                    _logger.info('CoinGate CSV import: currency mismatch, skipping transaction #%s', transaction_id)
                    continue
                prev_lines = AccountBankStatementLine.search_count([
                    ('entry_reference', '=', transaction_id),
                    ('journal_id', '=', self.journal_id.id)
                ])
                if prev_lines:
                    continue
                partner_name = line_vals.get('partneris', '')

                partner_id = self.get_partner_id(partner_name=partner_name) if partner_name else False
                label = ' -- '.join(desc for desc in [line_vals.get('title'), line_vals.get('merchant order id')] if desc)
                amount = str2float(line_vals.get('total amount', '0'), self.decimal_separator)
                amount_eur = str2float(line_vals.get('amount eur', '0'), self.decimal_separator)
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': 'CoinGate CSV import',
                    'imported_partner_name': partner_name,
                    'amount': amount,
                    'currency_id': ccurrency.id,
                    'amount_currency': amount_eur,
                }
                lines.append(new_vals)
                fee = str2float(line_vals.get('coingate fee amount', '0'), self.decimal_separator)
                has_fee = not tools.float_is_zero(fee, precision_rounding=journal_currency.rounding)
                if has_fee:
                    fee_vals = new_vals.copy()
                    fee_eur = str2float(line_vals.get('fee eur', '0'), self.decimal_separator)
                    fee_vals.update({
                        'fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': -abs(fee),
                        'currency_id': ccurrency.id,
                        'amount_currency': -abs(fee_eur),
                    })
                    lines.append(fee_vals)
            if lines:
                statement = self._create_statement(lines)
                if statement:
                    statement_ids += [statement.id]

        return statement_ids

    def _process_lines_withdrawals(self, vals):
        """ Process withdrawal CSV files """
        statement_ids = []
        AccountBankStatementLine = self.env['account.bank.statement.line']

        journal_currency = self.journal_id.currency_id or self.env.user.company_id.currency_id
        ccurrency = self.env.user.company_id.currency_id

        date_format = self.force_date_format or self._guess_date_format(vals)
        datetimes = {}
        for day in vals:
            try:
                date = datetime.strptime(day, date_format)
            except ValueError:  # if there was a forced format, it was not checked
                raise exceptions.UserError(_('Neteisingas datos formatas.'))
            datetimes[day] = date

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')
                currency_code = line_vals.get('currency', '')
                if currency_code.upper() != journal_currency.name:
                    _logger.info('CoinGate CSV import: currency mismatch, skipping transaction #%s', transaction_id)
                    continue
                prev_lines = AccountBankStatementLine.search_count([
                    ('entry_reference', '=', transaction_id),
                    ('journal_id', '=', self.journal_id.id)
                ])
                if prev_lines:
                    continue

                amount = - str2float(line_vals.get('amount', '0'), self.decimal_separator)
                amount_eur = - str2float(line_vals.get('suma eur', '0'), self.decimal_separator)
                label = line_vals.get('payout description')
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': 'CoinGate withdrawal',
                    'amount': amount,
                    'currency_id': ccurrency.id,
                    'amount_currency': amount_eur,
                }
                lines.append(new_vals)

            if lines:
                statement = self._create_statement(lines)
                if statement:
                    statement_ids += [statement.id]

        return statement_ids

    def _create_statement(self, lines):
        if lines:
            # Ref needed objects
            AccountBankStatement = self.env['account.bank.statement']

            date = lines[0]['date']
            statement = AccountBankStatement.search([
                ('journal_id', '=', self.journal_id.id),
                ('sepa_imported', '=', True),
                ('date', '=', date)], limit=1,
            )
            lines.sort(key=lambda l: l.get('created_at'))

            if not statement:
                statement = AccountBankStatement.create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'CoinGate import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]

            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            statement.write({'line_ids': [(0, 0, line) for line in nonfee_lines]})

            for line in fee_lines:
                orig_line = statement.line_ids.filtered(
                    lambda x: x.entry_reference == line['entry_reference']
                )
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            # Write lines and balances to the statement
            statement.write({
                'line_ids': [(0, 0, line) for line in fee_lines],
                'balance_end_real': statement.balance_end,
                'balance_end_factual': statement.balance_end,
            })
            return statement
