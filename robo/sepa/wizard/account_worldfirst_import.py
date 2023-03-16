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


_input_fields = {'date', 'reference', 'description', 'value', 'available balance', 'fee', 'fee currency', 'notes'}


class AccountWorldfirstImport(models.TransientModel):

    _name = 'account.worldfirst.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'worldfirst')]")
    force_date_format = fields.Selection(selection_add=[('%d-%b-%Y', 'DD-Mon-YYYY')])

    def _get_input_fields(self):
        input_fields = _input_fields
        currency = (self.journal_id.currency_id or self.env.user.company_id.currency_id).name.lower()
        input_fields.update(['in (%s)' % currency, 'out (%s)' % currency])
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių WorldFirst operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'reference'),
                             (_('Suma'), 'value'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti WorldFirst operacijų')

    def _preprocess_vals(self, vals):
        journal_currency = (self.journal_id.currency_id or self.env.user.company_id.currency_id).name
        balance = vals.get('available balance', '0')
        if journal_currency in balance:
            balance = balance.replace(journal_currency, '').strip()
        try:
            balance = str2float(balance, self.decimal_separator)
        except:
            vals['reason'] = _('Could not convert balance field')
            return False
        vals['balance_end'] = balance
        if any('%s (%s)' % (key, journal_currency.lower()) not in vals for key in ['in', 'out']):
            vals['reason'] = _('Entry does not seem to be in the right currency')
            return False
        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        journal_currency = self.journal_id.currency_id or self.env.user.company_id.currency_id

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
                transaction_id = '-'.join(line_vals.get(key, 'x') for key in ['date', 'value', 'reference', 'note'])
                prev_lines = stmtl_obj.search([('entry_reference', '=', transaction_id),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_id = self.get_partner_id(partner_name=line_vals.get('description'))
                label = line_vals.get('reference')
                amount = str2float(line_vals.get('value', '0'), self.decimal_separator)
                if line_vals.get('line_is_payout'):
                    amount = - amount
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('notes'),
                    'imported_partner_name': line_vals.get('description', ''),
                    'amount': amount,
                    'balance_end': line_vals.get('balance_end'),
                }
                lines.append(new_vals)
                fee = str2float(line_vals.get('fee', '0'), self.decimal_separator)
                has_fee = not tools.float_is_zero(fee, precision_rounding=journal_currency.rounding)
                if has_fee and line_vals.get('fee currency') == journal_currency.name:
                    fee_vals = new_vals.copy()
                    fee_vals.update({
                        'fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': -abs(fee),
                    })
                    new_vals['amount'] += abs(fee)
                    lines.append(fee_vals)

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
                    'name': 'WorldFirst import',
                    'sepa_imported': True,
                    'balance_end_real': lines[0]['balance_end']
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]
            for line in nonfee_lines:
                for key in ['balance_end']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = stm_line_obj.search([('entry_reference', '=', line['entry_reference']),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            return statement


AccountWorldfirstImport()
