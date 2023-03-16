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

_input_fields = {u'data',
                 u'mokėtojas / gavėjas',
                 u'mokėjimo nr.',
                 u'mokėjimo būdas',
                 u'bankas',
                 u'banko sąskaita',
                 u'užsakymo nr.',
                 u'paskirtis',
                 u'Įskaitymai (eur)',
                 u'nurašymai (eur)',
                 u'komisiniai (eur)',
                 u'likutis (eur)'
}


class AccountOPAYImport(models.TransientModel):

    _name = 'account.opay.import'
    _inherit = 'sepa.csv.importer'

    @staticmethod
    def _default_codepage():
        return 'iso8859_13'

    @staticmethod
    def _default_lines_to_skip():
        return 10

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'opay')]")
    decimal_separator = fields.Selection(default=',')

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {'message': _('Nepavyko importuoti šių OPAY operacijų:'),
                'table_format': [(_('Eilutė'), 'line_nr'),
                                 (_('Mokėjimo Nr.'), unicode('mokėjimo nr.')),
                                 (_('Data'), 'data'),
                                 (_('Suma'), 'amount'),
                                 (_('Partneris'), unicode('mokėtojas / gavėjas')),
                                 (_('Paskirtis'), 'paskirtis')]
                }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti OPAY operacijų')

    def _preprocess_vals(self, vals):
        res = True
        credit = str2float(vals.get(unicode('Įskaitymai (eur)'), '0'), self.decimal_separator)
        debit = str2float(vals.get(unicode('nurašymai (eur)'), '0'), self.decimal_separator)
        fee = str2float(vals.get('komisiniai (eur)', '0'), self.decimal_separator)
        balance = str2float(vals.get('likutis (eur)', '0'), self.decimal_separator)
        date = vals.get('data')
        vals.update(date=date, amount=credit-debit, fee=fee, balance=balance)
        if tools.float_is_zero(credit-debit, precision_digits=2) and tools.float_is_zero(fee, precision_digits=2):
            res = False
        if not date:
            res = False
        return res

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
                transaction_id = line_vals.get(unicode('mokėjimo nr.'))
                prev_lines = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_id = self.get_partner_id(partner_name=line_vals.get(unicode('mokėtojas / gavėjas'), ''))
                amount = line_vals.get('amount')
                label = line_vals.get('paskirtis') or '/'
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label,
                    'imported_partner_name': line_vals.get(unicode('mokėtojas / gavėjas')),
                    'amount': amount,
                    'balance_end': line_vals.get('balance', False),
                    'balance_start': line_vals.get('balance') - line_vals.get('amount') + line_vals.get('fee'),
                }
                fee = line_vals.get('fee')
                rounding = self.journal_id.currency_id.rounding if self.journal_id.currency_id else 0.01
                has_fee = not tools.float_is_zero(fee, precision_rounding=rounding)
                is_fee = has_fee and tools.float_is_zero(amount, precision_rounding=rounding)
                if is_fee:
                    exp = r'\[:([0-9abcdef]+)\]$'
                    m = re.search(exp, label)
                    if m and len(m.groups()) == 1:
                        new_vals.update(commision_of_transaction_id=m.groups()[0])
                    new_vals.update({'amount': -fee, 'fee': True})
                elif has_fee:
                    fee_vals = new_vals.copy()
                    fee_vals.update({
                        'fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': -fee,
                        'partner_id': False,
                    })
                lines.append(new_vals)
                if has_fee and not is_fee:
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
                    'name': 'OPAY import',
                    'sepa_imported': True,
                    'balance_end_real': lines[-1]['balance_end'],
                    'balance_start': lines[0]['balance_start'],
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if line.get('fee')]
            nonfee_lines = [line for line in lines if not line.get('fee')]
            for line in nonfee_lines:
                for key in ['balance_end']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                ref_entry = line.get('commision_of_transaction_id', line['entry_reference'])
                orig_line = stm_line_obj.search([('entry_reference', '=', ref_entry),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if ref_entry and orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'balance_end', 'commision_of_transaction_id']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountOPAYImport()
