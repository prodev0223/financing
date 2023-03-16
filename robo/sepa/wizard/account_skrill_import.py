# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import re
import pytz
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)

SKRILL_DATE_FORMAT = '%d %b %y %H:%M'

_input_fields = {'type', 'transaction details', '[+]', '[-]', 'currency', 'time (cet)',
                 'id', 'status', 'balance', 'more information'}


class AccountSkrillImport(models.TransientModel):

    _name = 'account.skrill.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'skrill')]")

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Skrill operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction_id'),
                             (_('Data'), 'time (cet)'),
                             (_('Aprašymas'), 'more information'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Skrill operacijų')

    def _preprocess_vals(self, vals):
        status = vals.get('status', 'processed')
        if status != 'processed':
            vals['reason'] = _("Būsena yra ne 'processed' (%s)") % status
        transaction_id = vals.get('id')
        if not transaction_id:
            vals['reason'] = _('ID lauko nėra')
            return False
        vals['transaction_id'] = transaction_id
        if not('[-]' in vals and '[+]' in vals):
            vals['reason'] = _('[+] arba [-] lauko nėra')
            return False
        debit = str2float(vals.get('[-]') or '0', self.decimal_separator)
        credit = str2float(vals.get('[+]') or '0', self.decimal_separator)
        vals['amount'] = credit - debit
        date = vals.get('time (cet)')
        if date:
            try:
                date = datetime.strptime(date, SKRILL_DATE_FORMAT)
                date_dt = pytz.timezone('CET').localize(date).astimezone(pytz.timezone('Europe/Vilnius'))
                vals['date'] = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                vals['date_obj'] = date_dt
            except:
                vals['reason'] = _('Neįmanoma konvertuoti datos eilutės')
                return False
        else:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        currency_info = self._get_currency_info_from_lines(vals)
        # currency = currency_info['currency']

        for day in sorted(vals):
            lines = []
            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')
                prev_lines = stmtl_obj.search([('entry_reference', '=', transaction_id),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                transaction_details = line_vals.get('transaction details', '')
                try:
                    name = re.search(r'from ([\w\.\-]+@[\w\-\.]+\b)', transaction_details)
                    partner_email = name.group(1).strip() if name else ''
                except:
                    partner_email = ''

                partner_id = self.get_partner_id(partner_email=partner_email)
                label = ': '.join(desc for desc in [line_vals.get('type') , line_vals.get('more information')] if desc)
                amount = line_vals.get('amount', '0')
                new_vals = {
                    'date': day,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': transaction_details,
                    'imported_partner_name': partner_email or '',
                    'date_obj': line_vals.get('date_obj'),
                    'amount': amount,
                }
                if 'balance' in line_vals:
                    new_vals['balance_end'] = str2float(line_vals.get('balance') or '0', self.decimal_separator)
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
            lines.sort(key=lambda l: (l.get('date_obj'), l.get('transaction_id')))

            if not statement:
                st_vals =  {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Skrill import',
                    'sepa_imported': True,
                }
                balance_end = lines[-1].get('balance_end')
                if balance_end is not None:
                    st_vals['balance_end_real'] = balance_end
                    st_vals['balance_start'] = balance_end - sum(l['amount'] for l in lines)
                statement = self.env['account.bank.statement'].create(st_vals)

            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]
            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = stm_line_obj.search([('entry_reference', '=', line['entry_reference']),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountSkrillImport()
