# -*- encoding: utf-8 -*-
from __future__ import division
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
from odoo.tools import float_is_zero
import logging

_logger = logging.getLogger(__name__)

_input_fields = {u'Vertė datai', u'Užsakyta per', u'Tipas', u'Užsakymo numeris', u'Aprašymas', u'Keitimo kursas',
                 u'Debetas',  u'Kreditas'}


class AccountMypossImport(models.TransientModel):

    _name = 'account.mypos.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'mypos')]")

    def _get_input_fields(self):
        input_fields = {i.lower() for i in _input_fields}
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Could not import these MyPOS operations:'),
            'table_format': [(_('Line'), 'line_nr'),
                             (_('Date'), 'vertė datai'.decode('utf-8')),
                             (_('Description'), 'aprašymas'.decode('utf-8')),
                             (_('Reason'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Could not import myPOS operations')

    def _preprocess_vals(self, vals):
        date = vals.get('vertė datai'.decode('utf-8'))
        if not date:
            vals['reason'] = _('"Vertė datai" field not found')
            return False
        vals['date'] = date.split(' ')[0]

        transaction_type = vals.get('tipas')
        if not transaction_type:
            vals['reason'] = _('"Tipas" field not found')
            return False
        vals['transcation_type'] = transaction_type

        exchange_rate = vals.get('keitimo kursas')
        if not exchange_rate or float_is_zero(float(exchange_rate), precision_digits=3):
            vals['reason'] = _('Either field "Keitimo kursas" was not found or was not a floating point value')
            return False
        vals['exchange_rate'] = float(exchange_rate)

        try:
            debit = str2float(vals.get('debetas') or '0', self.decimal_separator)
        except Exception:
            vals['reason'] = _('Could not convert "Debetas" field value')
            return False
        vals['debit'] = debit

        try:
            credit = str2float(vals.get('kreditas') or '0', self.decimal_separator)
        except Exception:
            vals['reason'] = _('Could not convert "Kreditas" field value')
            return False
        vals['credit'] = credit

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
                transaction_id = '-'.join(str(line_vals.get(key, 'x')) for key in ['date', 'transaction_type',
                                                                                   'aprašymas'.decode('utf-8'),
                                                                                   'debit' or 'credit'])
                is_fee = 'fee' in line_vals.get('transcation_type', '')
                prev_lines = stmtl_obj.search([
                    ('entry_reference', '=', transaction_id),
                    ('journal_id', '=', self.journal_id.id),
                ], limit=1)
                if prev_lines:
                    continue
                label = line_vals.get('aprašymas'.decode('utf-8'))
                amount = (line_vals.get('credit') or line_vals.get('debit') * (-1)) / line_vals.get('exchange_rate')
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': None,
                    'info_type': 'unstructured',
                    'name': label or '/',
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
                    'name': 'MyPos import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            fee_lines = [line for line in lines if 'is_fee' in line]
            nonfee_lines = [line for line in lines if 'is_fee' not in line]
            statement.write({'line_ids': [(0, 0, line) for line in nonfee_lines]})
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement
