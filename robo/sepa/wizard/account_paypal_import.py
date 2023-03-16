# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import pytz
import logging
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
from six import itervalues

_logger = logging.getLogger(__name__)


_input_fields = {'gross', 'net', 'fee', 'transaction id', 'date', 'name', 'currency', 'balance', 'from email address',
                 'to email address', 'balance impact', 'invoice number', 'type', 'status', 'description', 'time', 'time zone'}


class AccountPaypalImport(models.TransientModel):

    _name = 'account.paypal.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'paypal')]")

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių PayPal operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'transaction id'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'gross'),
                             (_('Būsena'), 'status'),
                             (_('Priežastis'), 'reason'),
                             ]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti PayPal operacijų')

    def _preprocess_vals(self, vals):
        if 'status' not in self._header_fields:
            vals.update({'status': 'completed'})
        # Only keeping Pending, Completed and Denied status
        if not vals.get('status'):
            vals['reason'] = _('Vienoje eilutėje trūksta lauko "status"')
            return False
        if vals.get('status', '').lower() not in ['pending', 'completed', 'denied']:
            vals['reason'] = _('Statusas "%s" nėra priimtina reikšmė') % vals.get('status')
            return False
        try:
            tz = pytz.timezone(vals.get('time zone', 'America/Los_Angeles'))
        except pytz.UnknownTimeZoneError:
            tz = None
        vals['tz'] = tz
        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

        # currency_info = self._get_currency_info_from_lines(vals)
        # currency = currency_info['currency']
        journal_currency = self.journal_id.currency_id or self.env.user.company_id.currency_id

        date_format = self.force_date_format or self._guess_date_format(vals)
        if all('time' in l and l['tz'] for d in vals for l in vals[d]):
            updated_vals = {}
            user_tz = pytz.timezone(self.env.context.get('tz') or 'Europe/Vilnius')
            for line_vals in itervalues(vals):
                for line in line_vals:
                    time = line['time']
                    time_format = '%H:%M:%S' if len(time.split(':')) == 3 else '%H:%M'
                    try:
                        date_dt = datetime.strptime(line['date'] + ' ' + time, date_format + ' ' + time_format)
                    except ValueError:  # if there was a forced format, it was not checked
                        raise exceptions.UserError(_('Neteisingas datos formatas.'))
                    date_local = line['tz'].localize(date_dt).astimezone(user_tz)
                    line['date'] = date_local.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    line['time'] = date_local.strftime(tools.DEFAULT_SERVER_TIME_FORMAT)
                    updated_vals.setdefault(date_local.strftime(tools.DEFAULT_SERVER_DATE_FORMAT), []).append(line)
        else:
            updated_vals = {}
            for day in sorted(vals):
                try:
                    date_dt = datetime.strptime(day, date_format)
                    date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                except ValueError:  # if there was a forced format, it was not checked
                    raise exceptions.UserError(_('Neteisingas datos formatas.'))
                updated_vals[date] = vals[day]

        for date in sorted(updated_vals):
            lines = []
            for line_vals in updated_vals[date]:
                transaction_id = line_vals.get('transaction id')
                currency = line_vals.get('currency')
                if currency != journal_currency.name:
                    _logger.info('Paypal CSV import: currency mismatch, skipping transaction #%s', transaction_id)
                    continue
                if line_vals.get('status').lower() == 'denied':
                    transaction_id += '_D'
                balance_impact = line_vals.get('balance impact', '').lower()
                if balance_impact and balance_impact not in ['debit', 'credit']:
                    # There are transactions moving from pending to completed, same id. Completed has "memo" in balance impact
                    continue
                label = ': '.join(desc for desc in [line_vals.get('type'), line_vals.get('description')] if desc)
                amount = str2float(line_vals.get('gross', '0'), self.decimal_separator)
                prev_line = stmtl_obj.search([('entry_reference', '=', str(transaction_id)),
                                              ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_line and not (label.startswith('Cancellation of')
                                      and tools.float_is_zero(amount + prev_line.amount,
                                                              precision_rounding=journal_currency.rounding)):
                    continue
                if balance_impact == 'credit':
                    partner_email = line_vals.get('from email address', '')
                else:
                    partner_email = line_vals.get('to email address', '')

                partner_id = self.get_partner_id(partner_name=line_vals.get('name', ''), partner_email=partner_email)
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('invoice number'),
                    'imported_partner_name': line_vals.get('name'),
                    'time': line_vals.get('time', '00'),
                    'amount': amount,
                }
                lines.append(new_vals)
                fee = str2float(line_vals.get('fee', '0'), self.decimal_separator)
                has_fee = not tools.float_is_zero(fee, precision_rounding=journal_currency.rounding)
                if has_fee:
                    fee_vals = new_vals.copy()
                    fee_vals.update({
                        'fee': True,
                        'name': (label + ' ({})' if label else '{}').format(_('Įmoka')),
                        'amount': fee,
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
            lines.sort(key=lambda l: l.get('time'))

            if not statement:
                statement = self.env['account.bank.statement'].create( {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Paypal import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            stm_line_obj = self.env['account.bank.statement.line']
            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]
            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'time']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in nonfee_lines]
            for line in fee_lines:
                orig_line = stm_line_obj.search([('entry_reference', '=', line['entry_reference']),
                                                 ('journal_id', '=', self.journal_id.id)], limit=1)
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'time']:
                    line.pop(key, None)
            statement.line_ids = [(0, 0, line) for line in fee_lines]
            statement.balance_end_real = statement.balance_end
            return statement


AccountPaypalImport()
