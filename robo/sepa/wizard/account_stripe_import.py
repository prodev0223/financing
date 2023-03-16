# -*- encoding: utf-8 -*-
from odoo.addons.queue_job.job import job
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import pytz
import re
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float

import logging

_logger = logging.getLogger(__name__)


_input_fields = {'gross', 'net', 'fee', 'balance_transaction_id', 'customer_name', 'currency', 'customer_facing_currency', 'description',
                 'id', 'created (utc)', 'available on (utc)', 'status', 'amount', 'created',
                 'payout_id', 'effective_at_utc', 'effective_at', 'reporting_category', 'payout_status', 'payout_type',
                 'customer_facing_amount', 'customer_email', 'customer_description', 'created_utc', 'available_on_utc'}


class AccountStripeImport(models.TransientModel):

    _name = 'account.stripe.import'
    _inherit = 'sepa.csv.importer'

    @api.model
    def default_get(self, fields_list):
        res = super(AccountStripeImport, self).default_get(fields_list)
        if 'skip_bank_statement_normalization' in fields_list and 'journal_id' in res:
            journal = self.env['account.journal'].browse(res['journal_id'])
            res['skip_bank_statement_normalization'] = journal and journal.skip_bank_statement_normalization or False
        return res

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'stripe')]")
    skip_bank_statement_normalization = fields.Boolean(string='Praleisti banko išrašų normalizavimą')

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Stripe operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('ID'), 'balance_transaction_id'),
                             (_('Data'), 'created_utc'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'gross'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Stripe operacijų')

    def _preprocess_vals(self, vals):
        reporting_category = vals.get('reporting_category', 'charge')
        if reporting_category == 'payout':
            # special case if we are importing Itemized payout report
            payout_id = vals.get('payout_id')
            if not payout_id:
                vals['reason'] = _('payout_id lauko nėra')
                return False
            transaction_id = vals.get('balance_transaction_id')
            if not transaction_id or not transaction_id.startswith('txn_'):
                vals['reason'] = _('balance_transaction_id lauko nėra')
                return False
            vals['transaction_id'] = transaction_id
            payout_status = vals.get('payout_status', 'paid')
            if payout_status != 'paid':
                vals['reason'] = _("Būsena yra ne 'paid' (%s)") % payout_status
                return False
            payout_type = vals.get('payout_type')
            if payout_type and payout_type != 'bank_account':
                vals['reason'] = _("payout_type %s dar nėra palaikomas. Susisiekite su sistemos administratoriumi"
                                   % payout_type)
                return False
            if 'gross' not in vals:  # For now, we only accept amounts in 'gross' column
                vals['reason'] = _('Nerastas sumos laukas')
                return False
            fee = str2float(vals.get('fee', '0'), self.decimal_separator)
            if not tools.float_is_zero(fee, precision_digits=2):
                vals['reason'] = _('Įmokų mokesčiai nėra palaikomi. Susisiekite su sistemos administratoriumi')
                return False
            utc = True
            date = vals.get('effective_at_utc')
            if not date:
                utc = False
                date = vals.get('effective_at')
            if not date:
                vals['reason'] = _('Nerastas datos laukas')
                return False
            if utc:
                try:
                    date = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                except ValueError:
                    vals['reason'] = _('Neteisingas datos formatas.')
                    return False
                user_tz = pytz.timezone(self.env.context.get('tz') or 'Europe/Vilnius')
                date = user_tz.fromutc(date).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            vals['date'] = date.split()[0]
            vals['line_is_payout'] = True
            return True

        status = vals.get('status', 'available')
        if status != 'available':
            vals['reason'] = _("Būsena yra ne 'available' (%s)") % status
            return False
        transaction_id = vals.get('balance_transaction_id')
        if not transaction_id:
            transaction_id = vals.get('id')
        if not transaction_id or not transaction_id.startswith('txn_'):
            vals['reason'] = _('balance_transaction_id lauko nėra')
            return False
        amount = vals.get('gross')
        if not amount:
            amount = vals.get('amount')
        if not amount:
            vals['reason'] = _('Nerastas sumos laukas')
            return False
        vals['gross'] = amount
        vals['transaction_id'] = transaction_id
        date = vals.get('created_utc')
        utc = True
        if not date:
            date = vals.get('created (utc)')
        if not date:
            utc = False
            date = vals.get('created')
        if not date:
            vals['reason'] = _('Nerastas datos laukas')
            return False
        if utc:
            try:
                date = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                vals['reason'] = _('Neteisingas datos formatas.')
                return False
            user_tz = pytz.timezone(self.env.context.get('tz') or 'Europe/Vilnius')
            date = user_tz.fromutc(date).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        vals['date'] = date.split()[0]
        if reporting_category == 'payout_reversal':
            vals['reason'] = _("'reporting_category' (%s) is not supported. Please contact support") % reporting_category
            return False
        return True

    @job
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
            date = datetimes[day].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for line_vals in vals[day]:
                transaction_id = line_vals.get('transaction_id')
                currency_code = line_vals.get('currency', '')
                if currency_code.upper() != journal_currency.name:
                    _logger.info('Stripe CSV import: currency mismatch, skipping transaction #%s', transaction_id)
                    continue
                prev_lines = stmtl_obj.search([('entry_reference', '=', transaction_id),
                                               ('journal_id', '=', self.journal_id.id)], limit=1)
                if prev_lines:
                    continue
                partner_email = line_vals.get('customer_email', '')
                customer_description = line_vals.get('customer_description', '')
                partner_name = line_vals.get('customer_name', '')
                if not partner_name:
                    try:
                        name = re.search(r'Customer for ([^\(]*) \([^\)]*\)', customer_description)
                        partner_name = name.group(1).strip() if name else ''
                    except:
                        partner_name = ''

                partner_id = self.get_partner_id(partner_name=partner_name, partner_email=partner_email)
                label = ': '.join(desc for desc in [line_vals.get('type'), line_vals.get('description')] if desc)
                amount = str2float(line_vals.get('gross', '0'), self.decimal_separator)
                if line_vals.get('line_is_payout'):
                    amount = - amount
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'entry_reference': transaction_id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'ref': line_vals.get('invoice number'),
                    'imported_partner_name': partner_name or line_vals.get('customer_description', ''),
                    'created_at': line_vals.get('created_utc') or line_vals.get('created (utc)'),
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
                        'amount': -abs(fee),
                    })
                    lines.append(fee_vals)
                orig_currency = line_vals.pop('customer_facing_currency', None)
                if orig_currency and orig_currency != currency_code and not self.ignore_origin_currency:
                    amount_currency = str2float(line_vals.get('customer_facing_amount', '0'), self.decimal_separator)
                    line_currency = self.env['res.currency'].search([('name', '=ilike', orig_currency)])
                    if line_currency:
                        new_vals.update(amount_currency=amount_currency, currency_id=line_currency.id)

            if lines:
                statement = self._create_statement(lines)
                if statement:
                    statement_ids += [statement.id]

        if statement_ids and not self.skip_bank_statement_normalization:
            statement = self.env['account.bank.statement'].search([('id', 'in', statement_ids)],
                                                                  order='date, create_date', limit=1)
            self.env['account.bank.statement']._normalize_balances_ascending_from(statement)

        return statement_ids

    def _create_statement(self, lines):
        if lines:
            # Ref needed objects
            AccountBankStatement = self.env['account.bank.statement']
            AccountBankStatementLine = self.env['account.bank.statement.line']

            date = lines[0]['date']
            statement = AccountBankStatement.search([
                ('journal_id', '=', self.journal_id.id),
                ('sepa_imported', '=', True),
                ('date', '=', date)], limit=1,
            )
            lines.sort(key=lambda l: l.get('created_at'))

            if not statement:
                statement = AccountBankStatement.create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Stripe import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            fee_lines = [line for line in lines if 'fee' in line]
            nonfee_lines = [line for line in lines if 'fee' not in line]

            for line in nonfee_lines:
                for key in ['balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            statement.write({'line_ids': [(0, 0, line) for line in nonfee_lines]})
            for line in fee_lines:
                orig_line = statement.line_ids.filtered(
                    lambda x: x.entry_reference == line['entry_reference']
                )
                if orig_line:
                    line['commission_of_id'] = orig_line.id
                line['is_fee'] = True
                for key in ['fee', 'partner_id', 'imported_partner_name', 'balance_end', 'balance_start', 'created_at']:
                    line.pop(key, None)

            # Write lines and balances to the statement
            statement.write({
                'line_ids': [(0, 0, line) for line in fee_lines],
                'balance_end_real': statement.balance_end,
                'balance_end_factual': statement.balance_end,
            })
            return statement
