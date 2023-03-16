# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
import logging

_logger = logging.getLogger(__name__)

_input_fields = {'date', 'iban_account', 'sender_name', 'recipient_name', 'payment_details', 'amount', 'currency',
                 'tran_id', }


class AccountWallettoImport(models.TransientModel):

    _name = 'account.walletto.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'walletto')]")

    def _get_input_fields(self):
        input_fields = _input_fields
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Could not import these Walletto operations:'),
            'table_format': [(_('Line'), 'line_nr'),
                             (_('Date'), 'date'),
                             (_('Transaction id'), 'tran_id'),
                             (_('Payment details'), 'payment_details'),
                             (_('Reason'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Could not import Walletto operations')

    def _preprocess_vals(self, vals):
        date = vals.get('date')
        if not date:
            vals['reason'] = _('Date field not found')
            return False
        vals['date'] = date.split(' ')[0]
        transaction_id = vals.get('tran_id')
        if not transaction_id:
            vals['reason'] = _('ID field not found')
            return False
        vals['transaction_id'] = transaction_id
        iban_account = vals.get('iban_account')
        if not iban_account or iban_account != self.journal_id.bank_acc_number:
            vals['reason'] = _('IBAN account not provided')
            return False
        if not vals.get('amount'):
            vals['reason'] = _('Amount field not found')
            return False
        try:
            amount = str2float(vals.get('amount') or '0', self.decimal_separator)
        except Exception:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = amount
        currency = vals.get('currency')
        if not currency or currency != (self.journal_id.currency_id or self.env.user.company_id.currency_id).name:
            vals['reason'] = _('Currency field is not correct')
            return False
        vals['currency'] = currency

        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        date_format = self.force_date_format or self._guess_date_format(vals)
        datetimes = {}
        for day in vals:
            try:
                date = datetime.strptime(day, date_format)
            except ValueError:  # if there was a forced format, it was not checked
                raise exceptions.UserError(_('Incorrect date format'))
            datetimes[day] = date

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')

                prev_lines = stmtl_obj.search([
                    ('entry_reference', '=', transaction_id),
                    ('journal_id', '=', self.journal_id.id),
                ], limit=1)
                if prev_lines:
                    continue

                partner_name = line_vals.get('sender_name') or line_vals.get('recipient_name')
                partner_id = self.get_partner_id(partner_name=partner_name)

                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'imported_partner_name': partner_name,
                    'name': line_vals.get('payment_details', '/'),
                    'amount': line_vals.get('amount') or 0.0,
                    'info_type': 'unstructured',
                    'ref': 'Import from CSV file',
                }
                lines.append(new_vals)
            if lines:
                statement = self._create_statement(lines)
                if statement:
                    statement_ids += [statement.id]
        return statement_ids

    def _create_statement(self, lines):
        if lines:
            date = lines[0]['date']
            statement = self.env['account.bank.statement'].search([
                ('journal_id', '=', self.journal_id.id),
                ('sepa_imported', '=', True),
                ('date', '=', date),
            ], limit=1)

            if not statement:
                statement = self.env['account.bank.statement'].create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Walletto import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            statement.line_ids = [(0, 0, line) for line in lines]
            statement.balance_end_real = statement.balance_end
            return statement
