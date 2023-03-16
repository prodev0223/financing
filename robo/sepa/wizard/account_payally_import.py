# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import re
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
import logging


_logger = logging.getLogger(__name__)


_input_fields = {'date', 'id', 'details', 'debit',  'credit', 'beneficiary/payer', 'balance'}


class AccountPayallyImport(models.TransientModel):

    _name = 'account.payally.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'payally')]")

    def _get_input_fields(self):
        input_fields = _input_fields
        currency = (self.journal_id.currency_id or self.env.user.company_id.currency_id).name.lower()
        input_fields.update(['in (%s)' % currency, 'out (%s)' % currency])
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių PayAlly operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'details'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti PayAlly operacijų')

    def _preprocess_vals(self, vals):
        transaction_id = vals.get('id')
        if not transaction_id:
            vals['reason'] = _('ID lauko nėra')
            return False
        vals['transaction_id'] = transaction_id
        if not('debit' in vals and 'credit' in vals):
            vals['reason'] = _('Debit arba Credit lauko nėra')
            return False
        try:
            debit = str2float(vals.get('debit') or '0', self.decimal_separator)
            credit = str2float(vals.get('credit') or '0', self.decimal_separator)
        except:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = credit - debit
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
                transaction_id = line_vals.get('id')
                details = line_vals.get('details', '')
                is_fee = True if re.search(r'Fees: [0-9]+', details) else False
                prev_line_domain = [('entry_reference', '=', transaction_id),
                                    ('journal_id', '=', self.journal_id.id),
                                    ('is_fee', '=', is_fee)]
                if details == 'Account monthly fee':
                    # it seems the same ID is provided for multiple transactions of monthly fee
                    prev_line_domain.append(('date', '=', date))
                prev_line = stmtl_obj.search_count(prev_line_domain)
                if prev_line:
                    continue
                partner_name = line_vals.get('beneficiary/payer')
                partner_id = False
                if not is_fee:
                    partner_id = self.get_partner_id(partner_name=partner_name)
                label = line_vals.get('details')
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': False,
                    'imported_partner_name': partner_name,
                    'amount': line_vals['amount'],
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
            statement = self.env['account.bank.statement'].search([('journal_id', '=', self.journal_id.id),
                                                                   ('sepa_imported', '=', True),
                                                                   ('date', '=', date)], limit=1)

            if not statement:
                statement = self.env['account.bank.statement'].create( {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'PayAlly import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if line.get('is_fee')]
            nonfee_lines = [line for line in lines if not line.get('is_fee')]
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = stm_line_obj.search([('entry_reference', '=', line['entry_reference']),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                for key in ['partner_id', 'imported_partner_name']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountPayallyImport()
