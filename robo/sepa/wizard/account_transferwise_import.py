# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from datetime import datetime
from collections import defaultdict

from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)

_input_fields = {'transferwise id', 'date', 'amount', 'currency', 'description', 'payment reference', 'running balance',
                 'payer name', 'payee name', 'total fees'}


class AccountTransferwiseImport(models.TransientModel):
    _name = 'account.transferwise.import'
    _inherit = 'sepa.csv.importer'
    _description = """ Import Wizard for TransferWise statements CSV file """

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių TransferWise operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction id'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'gross')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti TransferWise operacijų')

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'transferwise')]")

    @api.multi
    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        currency_info = self._get_currency_info_from_lines(vals)
        currency = currency_info['currency']

        date_format = self.force_date_format or self._guess_date_format(vals)
        datetimes = {}
        for day in vals:
            try:
                date = datetime.strptime(day, date_format)
            except ValueError:  # if there was a forced format, it was not checked
                raise exceptions.UserError(_('Neteisingas datos formatas.'))
            datetimes[day] = date

        transaction_ids_to_import = []
        for transactions_by_day in vals.values():
            transaction_ids_to_import += [
                str(transaction.get('transferwise id', '')) for transaction in transactions_by_day
            ]
        existing_transactions = stmtl_obj.search([
            ('entry_reference', 'in', transaction_ids_to_import),
            ('journal_id', '=', self.journal_id.id)
        ])
        existing_transactions_by_day = defaultdict(list)
        for t in existing_transactions:
            existing_transactions_by_day[t.date].append(t)

        for day in sorted(vals, key=lambda d: datetimes[d]):
            lines = []
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            existing_date_transactions = existing_transactions_by_day[date]

            for line_vals in vals[day]:
                transaction_id = line_vals.get('transferwise id')
                existing_lines = [t for t in existing_date_transactions if t.entry_reference == transaction_id]
                amount = str2float(line_vals.get('amount', '0'), self.decimal_separator)
                # Allow maximum of two lines with same transaction id but only if the amounts are opposite
                if existing_lines:
                    if len(existing_lines) > 1:
                        continue  # Multiple lines already exist - don't create another one
                    existing_line = existing_lines[0]
                    if tools.float_compare(existing_line.amount, -amount, precision_digits=2) != 0:
                        # The amount is not the opposite of the existing amount
                        continue
                line_description = line_vals.get('description') or '/'
                if line_description.startswith('Wise Charges'):
                    # Get amount from current charges line to add to the original line, add it and skip current line
                    line_to_adjust = lines[-2] if len(lines) >= 2 else False
                    if not line_to_adjust or line_to_adjust.get('entry_reference', str()) != transaction_id or \
                            line_to_adjust.get('fee'):
                        raise exceptions.UserError(_('Nerasta eilutė, kuriai pridėti mokesčius. '
                                                     'Kreipkitės į sistemos administratorių.'))
                    line_to_adjust['orig_amount'] += amount
                    line_to_adjust['amount'] += amount
                    continue

                if tools.float_compare(amount, 0.0, precision_rounding=currency.rounding) > 0:
                    partner_name = line_vals.get('payer name', False)
                else:
                    partner_name = line_vals.get('payee name', False)

                partner_id = self.get_partner_id(partner_name=partner_name)
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': line_description,
                    'ref': line_vals.get('invoice number'),
                    'imported_partner_name': partner_name,
                    'balance_end': str2float(line_vals.get('running balance', '0'), self.decimal_separator),
                    'orig_amount': amount
                }
                fee = str2float(line_vals.get('total fees', '0'), self.decimal_separator)
                has_fee = not tools.float_is_zero(fee, precision_rounding=currency.rounding)
                amount_fee_vals = {}
                if has_fee:
                    fee_vals = new_vals.copy()
                    fee_vals.update({'fee': True, 'name': line_vals.get('description') + _(' (Fee)')})
                    amount_fee_vals = {'amount': -fee}
                    sign = tools.float_compare(amount, 0.0, precision_rounding=currency.rounding)
                amount = sign * (abs(amount) - fee) if has_fee else amount
                amount_vals = {'amount': amount}

                new_vals.update(amount_vals)
                lines.append(new_vals)
                if has_fee:
                    fee_vals.update(amount_fee_vals)
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
                                                                   ('state', '=', 'open'),
                                                                   ('date', '=', date)], limit=1)
            lines.sort(key=lambda l: l.get('transferwise id'))

            if not statement:
                end_balances = [line['balance_end'] for line in filter(lambda l: not l.get('fee'), lines)]
                start_balances = [line['balance_end'] - line['orig_amount']
                                  for line in filter(lambda l: not l.get('fee'), lines)]
                end_balance = []
                while end_balances:
                    value = end_balances.pop()
                    if value in start_balances:
                        start_balances.remove(value)
                    else:
                        end_balance.append(value)

                if len(end_balance) == 1:
                    write_balances = True
                    start_balance = end_balance[0] - sum(line.get('amount') for line in lines)
                else:
                    write_balances = False

                vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Transferwise import',
                    'sepa_imported': True,
                }
                if write_balances:
                    vals.update({'balance_end_real': end_balance[0], 'balance_start': start_balance})

                statement = self.env['account.bank.statement'].create(vals)

            StatementLine = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]
            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'time', 'orig_amount']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = StatementLine.search([('entry_reference', '=', line['entry_reference']),
                                                  ('is_fee', '=', False),
                                                  ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'time',
                            'orig_amount']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            return statement


AccountTransferwiseImport()
