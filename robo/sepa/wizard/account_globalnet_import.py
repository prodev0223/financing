# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)


_input_fields = {'transaction id', 'date', 'sender/recipient', 'transaction type', 'amount', 'balance'}


class AccountGlobalnetImport(models.TransientModel):

    _name = 'account.globalnet.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'globalnet')]")


    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Global-Net operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction id'),
                             (_('Tipas'), 'transaction type'),
                             (_('Data'), 'date'),
                             (_('Suma'), 'amount'),
                             (_('Partneris'), 'sender/recipient')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Global-Net operacijų')

    def _preprocess_vals(self, vals):
        for f in _input_fields:
            if not vals.get(f):
                return False
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
                transaction_id = line_vals.get('transaction id')
                prev_lines = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_id = self.get_partner_id(partner_name=line_vals.get('sender/recipient', ''))
                amount = str2float(line_vals.get('amount', '0'), self.decimal_separator)
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': line_vals.get('transaction type') or '/',
                    'imported_partner_name': line_vals.get('sender/recipient'),
                    'amount': amount,
                    'balance_end': str2float(line_vals.get('balance', '0'), self.decimal_separator),
                }
                if line_vals.get('transaction type', '').endswith('Fees') :
                    new_vals.update({'fee': True})
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
            lines.reverse() # for balance, it seems that statements lines are in antechronological order

            if not statement:
                statement = self.env['account.bank.statement'].create( {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Global-Net import',
                    'sepa_imported': True,
                    'balance_end_real': lines[-1]['balance_end'],
                    'balance_start': lines[0]['balance_end'] - lines[0]['amount']
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
                for key in ['fee', 'partner_id', 'balance_end',]:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountGlobalnetImport()
