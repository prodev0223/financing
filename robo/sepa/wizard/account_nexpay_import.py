# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import _, fields, models, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
import re

_input_fields = {'Date', 'Beneficiary / Sender', 'Account number', 'Details', 'Amount (EUR)', 'Balance (EUR)',
                 'Payment number'}


class AccountNexpayImport(models.TransientModel):

    _name = 'account.nexpay.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'nexpay')]")

    def _get_input_fields(self):
        input_fields = {i.lower() for i in _input_fields}
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Could not import these Nexpay operations:'),
            'table_format': [(_('Line'), 'line_nr'),
                             (_('Date'), 'Date'),
                             (_('Payment No'), 'Payment number'),
                             (_('Payment details'), 'Details'),
                             (_('Reason'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Could not import Nexpay operations')

    def _preprocess_vals(self, vals):
        date = vals.get('date')
        if not date:
            vals['reason'] = _('Date field not found')
            return False
        vals['date'] = date.split(' ')[0]
        transaction_id = vals.get('payment number')
        if not transaction_id:
            vals['reason'] = _('Payment number field not found')
            return False
        vals['transaction_id'] = transaction_id

        if not vals.get('amount (eur)'):
            vals['reason'] = _('Amount (EUR) field not found')
            return False
        try:
            amount = str2float(vals.get('amount (eur)') or '0', self.decimal_separator)
        except Exception:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = amount

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
                is_fee = 'fee' in line_vals.get('details', '') or line_vals.get('beneficiary / sender') == 'NexPay, UAB'
                prev_lines = stmtl_obj.search([
                    ('entry_reference', '=', transaction_id),
                    ('journal_id', '=', self.journal_id.id),
                ], limit=1)
                if prev_lines:
                    continue

                partner_name = line_vals.get('beneficiary / sender')
                partner_id = self.get_partner_id(partner_name=partner_name)
                label = line_vals.get('details')
                amount = line_vals.get('amount')

                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('invoice number'),
                    'imported_partner_name': partner_name or line_vals.get('beneficiary / sender', ''),
                    'amount': amount,
                }
                if is_fee:
                    new_vals['is_fee'] = True
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
                ('date', '=', date)
            ], limit=1)

            if not statement:
                statement = self.env['account.bank.statement'].create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Nexpay import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            fee_lines = [line for line in lines if 'is_fee' in line]
            nonfee_lines = [line for line in lines if 'is_fee' not in line]

            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            statement.write({'line_ids': [(0, 0, line) for line in nonfee_lines]})
            for line in fee_lines:
                reference = re.findall(r'\d+', line['name'])
                if reference:
                    orig_line = statement.line_ids.filtered(
                        lambda x: x.entry_reference == reference[0]
                    )
                    if orig_line:
                        line['commission_of_id'] = orig_line.id
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement
