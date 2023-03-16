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

_input_fields = {'date', 'date started', 'date completed', 'date started (utc)', 'date completed (utc)',
                 'time', 'time started', 'time completed', 'time started (utc)', 'time completed (utc)',
                 'state', 'type', 'description', 'reference', 'orig currency', 'orig amount',
                 'payment currency', 'amount', 'fee', 'balance', 'account', 'id'}


def find_partner_name(transaction_type, desc):
    """
    Parse data from revolut transactions to guess a partner name
    :param transaction_type: transaction type as str
    :param desc: description as str
    :return: partner name as a str
    """
    #TODO: Check data in client systems to find out about other type style
    partner_name = ''
    desc = desc or ''
    if transaction_type in ['card_payment', 'CARD_PAYMENT']:
        partner_name = desc.replace('Card Payment to', '')
    elif transaction_type in ['transfer', 'TRANSFER']:
        if desc.startswith('To '):
            partner_name = desc[len('To '):]
        if desc.startswith('Transfer to '):
            partner_name = desc[len('Transfer to '):]
    elif transaction_type in ['topup', 'TOPUP']:
        if desc.startswith('Payment from '):
            partner_name = desc[len('Payment from '):]
    return partner_name


class AccountRevolutImport(models.TransientModel):
    _name = 'account.revolut.import'
    _inherit = 'sepa.csv.importer'
    _description = """ Import Wizard for Revolut statements CSV files """

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Revolut operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'date'),
                             (_('Laikas'), 'time'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'amount'),
                             (_('Būsena'), 'state'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Revolut operacijų')

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'revolut')]")
    show_api_warning_message = fields.Boolean(compute='_compute_show_api_warning_message')

    @api.depends('journal_id')
    def _compute_show_api_warning_message(self):
        for rec in self:
            if rec.journal_id.revolut_account_id and not rec.journal_id.revolut_account_id.revolut_api_id.disabled:
                rec.show_api_warning_message = True

    def _preprocess_vals(self, vals):
        if 'id' in vals:
            vals['new_style'] = True
            transaction_id = vals.get('id')
            if not transaction_id:
                vals['reason'] = _('ID laukas nenustatytas')
                return False
            vals['transaction_id'] = transaction_id
        else:
            state = vals.get('state')
            if not state or state.lower() != 'completed':
                vals['reason'] = _("Būsena yra ne 'completed' (%s)") % state
                return False
        currency = vals.get('payment currency')
        vals['currency'] = currency
        date, time = vals.get('date'), vals.get('time')
        if not date:
            date, time = vals.get('date completed'), vals.get('time completed')
        if not date:
            date, time = vals.get('date completed (utc)'), vals.get('time completed (utc)')
        if not date:
            date, time = vals.get('date started'), vals.get('time started')
        if not date:
            date, time = vals.get('date started (utc)'), vals.get('time started (utc)')
        if not date:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        vals.update(date=date)
        if time:
            vals.update(time=time)
        return True

    @api.multi
    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        journal_currency = self.journal_id.currency_id or self.env.user.company_id.currency_id

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
            date_dt = datetimes[day]
            date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')
                if not transaction_id:
                    if 'date started' in line_vals and 'time started' in line_vals:
                        date_key, time_key = 'date started', 'time started'
                    elif 'date started (utc)' in line_vals and 'time started (utc)' in line_vals:
                        date_key, time_key = 'date started (utc)', 'time started (utc)'
                    else:
                        date_key, time_key = 'date', 'time'
                    line_vals['date_fmt'] = date_dt.strftime('%Y-%m-%d')
                    transaction_id = '-'.join([line_vals.get(v,'NDEF') for v in ['date_fmt', time_key, 'type', 'description']])
                currency_code = line_vals.get('currency', '')
                if currency_code.upper() != journal_currency.name:
                    _logger.info('Revolut CSV import: currency mismatch, skipping transaction #%s', transaction_id)
                    continue
                prev_lines = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue

                transaction_type = line_vals.get('type')
                desc = line_vals.get('description', '')
                partner_name = find_partner_name(transaction_type, desc)
                partner_id = self.get_partner_id(partner_name=partner_name)

                amount = str2float(line_vals.get('amount', '0'), self.decimal_separator)
                name = line_vals.get('description') or '/'
                if line_vals.get('reference'):
                    name += ' -- ' + line_vals.get('reference')
                new_vals = {
                    'date': date,
                    'time': line_vals.get('time'),
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': name,
                    'ref': line_vals.get('reference'),
                    'imported_partner_name': partner_name,
                    'amount': amount
                }

                orig_currency = line_vals.pop('orig currency', None)
                currency_code = line_vals.get('currency')
                if orig_currency and orig_currency != currency_code:
                    amount_currency = abs(str2float(line_vals.get('orig amount', '0'), self.decimal_separator))
                    if tools.float_compare(amount, 0, precision_digits=2) < 0:
                        amount_currency = -amount_currency
                    line_currency = self.env['res.currency'].search([('name', '=', orig_currency)])
                    if line_currency:
                        new_vals.update(amount_currency=amount_currency, currency_id=line_currency.id)

                if line_vals.get('balance'):
                    balance_end = str2float(line_vals.get('balance', '0'), self.decimal_separator)
                    new_vals.update({
                        'balance_end': balance_end,
                        'balance_start': balance_end - amount,
                    })
                fee = str2float(line_vals.get('fee', '0'), self.decimal_separator)
                has_fee = not tools.float_is_zero(fee, precision_rounding=journal_currency.rounding)
                if has_fee:
                    if 'balance_start' in new_vals:
                        new_vals['balance_start'] -= fee
                    fee_vals = new_vals.copy()
                    fee_vals.pop('amount_currency', None)
                    fee_vals.pop('currency_id', None)
                    fee_vals.update({'is_fee': True,
                                     'name': name + ' (%s)' % _('Įmoka'),
                                     'amount': fee})

                lines.append(new_vals)
                if has_fee:
                    lines.append(fee_vals)

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
            if lines and (lines[0].get('date') > lines[-1].get('date')
                          or lines[0].get('date') == lines[-1].get('date') and
                          lines[0].get('time') >= lines[-1].get('time')):
                # Revolut statements seem to come in antechronological order. Raises issue with balance computation when
                # completion time are identical, because sorting still keep the order they came in. In that case, we reverse the list.
                lines.reverse()
            lines.sort(key=lambda l: (l.get('date'), l.get('time')))

            if not statement:
                vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Revolut import',
                    'sepa_imported': True,
                }
                if 'balance_start' in lines[0] and 'balance_end' in lines[-1]:
                    balance_start = lines[0].get('balance_start')
                    balance_end = lines[-1].get('balance_end')
                    vals.update({'balance_end_real': balance_end, 'balance_start': balance_start})

                statement = self.env['account.bank.statement'].create(vals)
            if statement.state != 'open':
                statement.write({'state': 'open'})

            StatementLine = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if 'is_fee' in line]
            nonfee_lines = [line for line in lines if 'is_fee' not in line]
            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'time', 'orig_amount']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = StatementLine.search([('entry_reference', '=', line['entry_reference']),
                                                  ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                for key in ['partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'time',
                            'orig_amount']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            return statement


AccountRevolutImport()
