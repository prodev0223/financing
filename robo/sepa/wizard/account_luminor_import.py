# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from ..model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)


_input_fields = {'date', 'matching number', 'partner', 'balance impact', 'amount', 'transaction id', 'description',
                 'currency', 'balance', 'destination account number'}

""" Columns on the file: 
"Account number";"Date";"Date 2";"Matching number";"Destination account number";"Partner";"Balance impact";"Amount";"Unknown";"Transaction id";"Description";"Currency";"Code";"Balance";"Unknown 2" """

class AccountLuminorImport(models.TransientModel):

    _name = 'account.luminor.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'luminor')]")
    force_date_format = fields.Selection(selection_add=[('%d.%m.%Y', 'DD.MM.YYYY'),], default='%d.%m.%Y')
    csv_separator = fields.Selection(default=';')
    decimal_separator = fields.Selection(default=',')
    codepage = fields.Char(default='iso-8859-13')

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Luminor operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction_id'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Luminor operacijų')

    def _preprocess_vals(self, vals):
        if not vals.get('transaction id'):
            vals['reason'] = _('Nerastas transakcijos identifikatoriaus laukas')
            return False
        if not 'date' in vals:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        amount = vals.get('amount')
        if not amount:
            vals['reason'] = _('Nerastas sumos laukas')
            return False
        balance_impact = vals.get('balance impact')
        if not balance_impact or balance_impact not in ['C', 'D']:
            vals['reason'] = _('Nerastas balanso poveikio laukas')
            return False
        amount = str2float(amount, self.decimal_separator)
        vals['amount'] = -amount if balance_impact == 'D' else amount
        matching_number = vals.get('matching number')
        if matching_number:
            if not vals.get('destination account number') or vals.get('partner') == 'Luminor Bank AB':
                vals['is_fee'] = True
        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        currency_info = self._get_currency_info_from_lines(vals)
        currency = currency_info['currency']

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
                transaction_id = line_vals.get('transaction id')
                prev_lines = stmtl_obj.search([('entry_reference', '=', transaction_id),
                                               ('is_fee', '=', line_vals.get('is_fee', False)),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_name = line_vals.get('partner', '')
                partner_id = self.get_partner_id(partner_name=partner_name)
                label = line_vals.get('description')
                amount = line_vals['amount']
                balance = str2float(line_vals['balance'], self.decimal_separator) if line_vals.get('balance') else False
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('matching number', ''),
                    'imported_partner_name': partner_name,
                    'amount': amount,
                    'end_balance': balance,
                    'is_fee': line_vals.get('is_fee', False),
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
            statement = self.env['account.bank.statement'].search([('journal_id', '=', self.journal_id.id),
                                                                   ('sepa_imported', '=', True),
                                                                   ('date', '=', date)], limit=1)
            if not statement:
                statement = self.env['account.bank.statement'].create( {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Luminor import',
                    'sepa_imported': True,
                    'balance_end': lines[-1]['end_balance'],
                    'balance_start': lines[0]['end_balance'] - lines[0]['amount'],
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if line['is_fee']]
            nonfee_lines = [line for line in lines if not line['is_fee']]
            for line in nonfee_lines:
                for key in ['end_balance',]:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = stm_line_obj.search([('entry_reference', '=', line['entry_reference']),
                                                 ('is_fee', '=', False),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                for key in ['partner_id', 'imported_partner_name', 'end_balance']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountLuminorImport()
