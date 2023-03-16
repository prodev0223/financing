# -*- encoding: utf-8 -*-
from __future__ import division
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
import logging

_logger = logging.getLogger(__name__)

_input_fields = {'Date', 'Reference', 'Counter account name', 'Counter account number', 'Counter account bank',
                 'Payment type', 'Description', 'Instructed amount', 'Instructed currency', 'Gross amount',
                 'Gross currency', 'Fee amount', 'Fee currency', 'Net amount', 'Net currency'}


class AccountBitsafeImport(models.TransientModel):

    _name = 'account.bitsafe.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'bitsafe')]")

    def _get_input_fields(self):
        input_fields = {i.lower() for i in _input_fields}
        return input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Could not import these Bitsafe operations:'),
            'table_format': [(_('Line'), 'line_nr'),
                             (_('Date'), 'date'),
                             (_('Reference'), 'reference'),
                             (_('Description'), 'description'),
                             (_('Reason'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Could not import Bitsafe operations')

    def _preprocess_vals(self, vals):
        date = vals.get('date')
        if not date:
            vals['reason'] = _('Field "Date" not found')
            return False
        vals['date'] = date
        reference = vals.get('reference')
        if not reference:
            vals['reason'] = _('Field "Reference" not found')
            return False
        vals['reference'] = reference
        iban = vals.get('counter account number')
        if not iban:
            vals['reason'] = _('Field "Counter account number" not found')
            return False
        vals['iban'] = iban
        amount = vals.get('net amount')
        if not amount:
            vals['reason'] = _('Field "Net amount" not found')
            return False
        try:
            amount = str2float(amount or '0', self.decimal_separator)
        except Exception:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = amount
        currency = vals.get('net currency')
        company_currency = self.env.user.company_id.currency_id
        if (self.journal_id.currency_id and currency != self.journal_id.currency_id.name) or \
                (not self.journal_id.currency_id and currency != company_currency.name):
            vals['reason'] = _('Currency does not match journal currency')
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
                raise exceptions.UserError(_('Incorrect date format'))
            datetimes[day] = date

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                reference = line_vals.get('reference')

                prev_lines = stmtl_obj.search([
                    ('entry_reference', '=', reference),
                    ('journal_id', '=', self.journal_id.id),
                ], limit=1)
                if prev_lines:
                    continue
                partner_name = line_vals.get('counter account name')
                partner_id = self.get_partner_id(partner_name=partner_name)

                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': reference,
                    'partner_id': partner_id if partner_id else None,
                    'imported_partner_name': partner_name,
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
                    'name': 'Bitsafe import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            statement.line_ids = [(0, 0, line) for line in lines]
            statement.balance_end_real = statement.balance_end
            return statement
