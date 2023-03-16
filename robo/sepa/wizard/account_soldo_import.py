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


_input_fields = {'settled date', 'user', 'description', 'amount',  'fee', 'transaction id', 'user id', 'notes'}


class AccountSoldoImport(models.TransientModel):

    _name = 'account.soldo.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'soldo')]")

    def _get_input_fields(self):
        input_fields = _input_fields
        currency = (self.journal_id.currency_id or self.env.user.company_id.currency_id).name.lower()
        input_fields.update(['in (%s)' % currency, 'out (%s)' % currency])
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių SOLDO operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'settled date'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti SOLDO operacijų')

    def _preprocess_vals(self, vals):
        if 'settled date' not in vals:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        date = vals.get('settled date')
        vals['date'] = date.split()[0]
        fee = str2float(vals.get('fee', '0'), self.decimal_separator)
        if not tools.float_is_zero(fee, precision_digits=2):
            vals['reason'] = _('Non-zero fee is not handled yet. Please contact support')
            return False
        if 'amount' not in vals:
            vals['reason'] = _('Nerastas sumos laukas')
            return False
        amount = str2float(vals.get('amount', '0'), self.decimal_separator)
        if tools.float_is_zero(amount, precision_digits=2):
            vals['reason'] = _('A transaction cannot have 0 amount')
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
                raise exceptions.UserError(_('Neteisingas datos formatas.'))
            datetimes[day] = date

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                transaction_id = '-'.join(line_vals.get(key, 'x') for key in ['settled date', 'user', 'transaction id'])
                prev_lines = stmtl_obj.search([('entry_reference', '=', transaction_id),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_id = False
                if not line_vals.get('user id'):
                    partner_id = self.get_partner_id(partner_name=line_vals.get('user'))
                label = line_vals.get('description')
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('notes'),
                    'imported_partner_name': line_vals.get('user', '') if not line_vals.get('user id') else False,
                    'amount': line_vals['amount'],
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
                    'name': 'SOLDO import',
                    'sepa_imported': True,
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
            statement.balance_end_real = statement.balance_end
            return statement


AccountSoldoImport()
