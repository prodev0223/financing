# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import re
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)

_input_fields = {'disbursement_date',
                 'settlement_currency_sales_eur',
                 'discount_eur',
                 'per_transaction_fees_eur',
}


class AccountBraintreeBkImport(models.TransientModel):

    _name = 'account.braintree.bk.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'braintree_bk')]")
    partner_id = fields.Many2one('res.partner', string='Partneris', required=True)

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {'message': _('Nepavyko importuoti šių Braintree operacijų:'),
                'table_format': [(_('Eilutė'), 'line_nr'),
                                 (_('Data'), 'date'),
                                 (_('Suma'), 'amount'),
                                 (_('Paskirtis'), 'reason')]
                }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti BrainTree operacijų')

    def _preprocess_vals(self, vals):
        fee = str2float(vals.get('per_transaction_fees_eur', '0'), self.decimal_separator)
        discount = str2float(vals.get('discount_eur', '0'), self.decimal_separator)
        amount = str2float(vals.get('settlement_currency_sales_eur', '0'), self.decimal_separator)
        if tools.float_is_zero(amount, precision_digits=2):
            vals['reason'] = _('Amount is 0')
            return False
        vals['amount'] = amount
        vals['date'] = vals.get('disbursement_date')
        vals['fee'] = fee + discount
        return True

    def _process_lines(self, vals):
        if not self.partner_id:
            raise exceptions.UserError(_('You need to choose the partner'))
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
                transaction_id = line_vals.get('date')
                prev_lines = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                               ('partner_id', '=', self.partner_id.id),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue

                amount = line_vals.get('amount')
                label = 'Braintree daily disbursment import'
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': self.partner_id.id,
                    'info_type': 'unstructured',
                    'name': label,
                    'imported_partner_name': self.partner_id.name,
                    'amount': amount,
                }
                fee = line_vals.get('fee')
                rounding = self.journal_id.currency_id.rounding if self.journal_id.currency_id else 0.01
                has_fee = not tools.float_is_zero(fee, precision_rounding=rounding)
                lines.append(new_vals)
                if has_fee:
                    fee_vals = new_vals.copy()
                    fee_vals.update({
                        'fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': -abs(fee),
                    })
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
                    'name': 'Braintree import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if line.get('fee')]
            nonfee_lines = [line for line in lines if not line.get('fee')]
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                ref_entry = line.get('commision_of_transaction_id', line['entry_reference'])
                orig_line = stm_line_obj.search([('entry_reference', '=', ref_entry),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if ref_entry and orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'commision_of_transaction_id']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountBraintreeBkImport()
