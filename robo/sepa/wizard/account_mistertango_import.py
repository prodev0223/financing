# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime

from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
from hashlib import md5

import logging

_logger = logging.getLogger(__name__)

_input_fields = {'date time', 'date', 'beneficiary/payer', 'payee name', 'payer name', 'amount', 'currency', 'description', 'payment purpose',  'type', 'account'}


class AccountMistertangoImport(models.TransientModel):
    _name = 'account.mistertango.import'
    _inherit = 'sepa.csv.importer'
    _description = """ Import Wizard for MisterTango statements CSV file """

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių MisterTango operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'date time'),
                             (_('Suma'), 'amount'),
                             (_('Partneris'), 'beneficiary/payer')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti MisterTango operacijų')

    def _preprocess_vals(self, vals):
        if 'beneficiary/payer' not in vals:
            amount = vals.get('amount')
            if amount is None:
                return False
            neg = True if amount.startswith('-') else False
            if neg and 'payee name' in vals:
                vals['beneficiary/payer'] = vals['payee name']
            if not neg and 'payer name' in vals:
                vals['beneficiary/payer'] = vals['payer name']
        if 'currency' not in vals:
            vals.update(currency=self.journal_id.currency_id and self.journal_id.currency_id.name or 'EUR')
        if 'date time' not in vals and 'date' in vals:
            vals.update({'date time': vals.get('date')})
        date_time = vals.get('date time')
        if date_time:
            date = date_time.split()[0]
            vals.update(date=date)
            return True
        return False

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'mistertango')]")


    def line_skip_test(self, line):
        return line.startswith('Balance') or super(AccountMistertangoImport, self).line_skip_test(line)

    @api.multi
    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        self._get_currency_info_from_lines(vals) #USED AS A CHECK

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
                hash_str = '-'.join(str(line_vals.get(key, '')) for key in ['date time', 'beneficiary/payer', 'account'])
                transaction_id = md5(hash_str).hexdigest()
                prev_lines = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                line_vals.update(transaction_id=transaction_id)
                amount = str2float(line_vals.get('amount', '0'), self.decimal_separator)
                partner_name = line_vals.get('beneficiary/payer', False)
                partner_id = self.get_partner_id(partner_name=partner_name)
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': line_vals.get('description') or line_vals.get('payment purpose') or '/',
                    'ref': line_vals.get('invoice number', False),
                    'imported_partner_name': partner_name,
                    'amount': amount,
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
                                                                   ('state', '=', 'open'),
                                                                   ('date', '=', date)], limit=1)
            #TODO: create new id
            lines.sort(key=lambda l: l.get('transaction_id'))

            if not statement:
                vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Mistertango import',
                    'sepa_imported': True,
                }
                statement = self.env['account.bank.statement'].create(vals)

            # for line in lines:
            #     for key in ['balance_end', 'balance_start', 'time', 'orig_amount']:
            #         line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in lines]
            return statement


AccountMistertangoImport()

