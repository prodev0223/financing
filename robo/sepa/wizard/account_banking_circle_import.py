# -*- encoding: utf-8 -*-
from __future__ import division

from six import iteritems

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
import logging

_logger = logging.getLogger(__name__)

_input_fields = {'Transaction Date', 'Value Date', 'Credit', 'Debit', 'Balance', 'Reference Number', 'Description',
                 'Payment Details', 'Beneficiary/Remitter 1', 'Beneficiary/Remitter 2'}


class AccountBankingCircleImport(models.TransientModel):
    _name = 'account.banking.circle.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'banking_circle')]")

    @staticmethod
    def _get_input_fields():
        input_fields = {i.lower() for i in _input_fields}
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Could not import these Banking Circle operations:'),
            'table_format': [(_('Line'), 'line_nr'),
                             (_('Date'), 'date'),
                             (_('Reference Number'), 'reference number'),
                             (_('Description'), 'description'),
                             (_('Reason'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Could not import Banking Circle operations')

    def _preprocess_vals(self, vals):
        # date
        date = vals.get('transaction date')
        if not date:
            vals['reason'] = _('Field "Transaction Date" not found')
            return False
        vals['date'] = date

        # amount
        credit = vals.get('credit')
        debit = vals.get('debit')
        if not credit and not debit:
            vals['reason'] = _('Fields "Credit" and "Debit" are empty')
            return False
        if credit and debit:
            vals['reason'] = _('Fields "Credit" and "Debit" are both filled in, please select one')
            return False
        amount = ''
        try:
            if credit:
                amount = str2float(credit or '0', self.decimal_separator)
            elif debit:
                amount = -abs(str2float(debit or '0', self.decimal_separator))
        except Exception:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = amount

        # reference
        reference = vals.get('reference number')
        if not reference:
            vals['reason'] = _('Field "Reference Number" not found')
            return False
        vals['reference'] = reference

        # partner
        partner = vals.get('beneficiary/remitter 1')
        if not partner:
            vals['reason'] = _('Field "Beneficiary/Remitter 1" not found')
            return False
        vals['partner'] = partner

        return True

    def _process_lines(self, vals):
        statement_ids = []
        statement_line_obj = self.env['account.bank.statement.line']

        date_format = self.force_date_format or self._guess_date_format(vals)
        dates_dt = {}
        for day in vals:
            try:
                date = datetime.strptime(day, date_format)
            except ValueError:  # if there was a forced format, it was not checked
                raise exceptions.UserError(_('Invalid data format.'))
            dates_dt[day] = date

        references = []
        for date, date_vals in iteritems(vals):
            references += [l.get('reference') for l in date_vals]

        existing_lines = statement_line_obj.search([
            ('entry_reference', 'in', references),
            ('journal_id', '=', self.journal_id.id),
        ])

        for day in sorted(vals, key=lambda d: dates_dt[d]):
            lines = []
            date = dates_dt[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                reference = line_vals.get('reference')
                if existing_lines.filtered(lambda l: l.entry_reference == reference):
                    continue

                partner = line_vals.get('partner')
                partner_id = self.get_partner_id(partner_name=partner)

                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': reference,
                    'partner_id': partner_id if partner_id else None,
                    'imported_partner_name': partner,
                    'name': line_vals.get('description'),
                    'amount': line_vals.get('amount') or 0.0,
                    'info_type': 'unstructured',
                    'ref': 'Import from CSV file',
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
            statement = self.env['account.bank.statement'].search([
                ('journal_id', '=', self.journal_id.id),
                ('sepa_imported', '=', True),
                ('date', '=', date),
            ], limit=1)

            if not statement:
                statement = self.env['account.bank.statement'].create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Banking Circle import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            statement.line_ids = [(0, 0, line) for line in lines]
            statement.balance_end_real = statement.balance_end
            return statement
