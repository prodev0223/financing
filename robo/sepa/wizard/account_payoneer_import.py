# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import pytz
from datetime import datetime
from odoo import fields, models, _, exceptions, tools
from odoo.addons.sepa.model.csv_importer import str2float
from six import itervalues
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)

_input_fields = {'date', 'description', 'amount', 'currency', 'status'}


class AccountPayoneerImport(models.TransientModel):
    _name = 'account.payoneer.import'
    _inherit = 'sepa.csv.importer'

    journal_id = fields.Many2one(domain="[('import_file_type', '=', 'payoneer')]")

    @staticmethod
    def _get_input_fields():
        return _input_fields

    @staticmethod
    def _get_error_message_format():
        return {
            'message': _('Nepavyko importuoti šių Payoneer operacijų:'),
            'table_format': [(_('Eilutė'), 'line_nr'),
                             (_('Data'), 'date'),
                             (_('Aprašymas'), 'description'),
                             (_('Suma'), 'amount'),
                             (_('Priežastis'), 'reason')]
        }

    @staticmethod
    def _get_bug_subject():
        return _('Nepavyko importuoti Payoneer operacijų')

    def _preprocess_vals(self, vals):
        date = vals.get('date')
        if not date:
            vals['reason'] = _('"Date" field not found')
            return False
        vals['date'] = date
        amount = vals.get('amount')
        if not amount:
            vals['reason'] = _('"Amount" field not found')
            return False
        try:
            amount = str2float(vals.get('amount') or '0', self.decimal_separator)
        except:
            vals['reason'] = _('Could not convert amount')
            return False
        vals['amount'] = amount
        status = vals.get('status')
        if not status or status.lower() != 'completed':
            vals['reasons'] = _('"Status" is not "completed"')
            return False
        return True

    def _process_lines(self, vals):
        statement_ids = []
        stmtl_obj = self.env['account.bank.statement.line']

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

        # ADMIN TOOL
        if self._context.get('prevent_duplicates'):
            updated_vals = self.fix_vals(updated_vals)

        for date in sorted(updated_vals):
            lines = []
            for line_vals in updated_vals[date]:
                currency = line_vals.get('currency')
                label = line_vals.get('description')
                amount = line_vals['amount']
                if currency != self.journal_id.currency_id.name:
                    _logger.info('Payoneer CSV import: currency mismatch, skipping transaction: {0} {1} {2}'.format(
                        date, label, amount))
                    continue
                prev_lines = stmtl_obj.search([
                    ('journal_id', '=', self.journal_id.id),
                    ('date', '=', date),
                    ('name', '=', label),
                    ('amount', '=', amount),
                ], limit=1)
                if prev_lines and not self._context.get('prevent_duplicates'):
                    continue
                partner_id = False
                new_vals = {
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'partner_id': partner_id if partner_id else None,
                    'info_type': 'unstructured',
                    'name': label or '/',
                    'amount': line_vals['amount'],
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
                                                                   ('date', '=', date)], limit=1)

            if not statement:
                statement = self.env['account.bank.statement'].create({
                    'date': date,
                    'journal_id': self.journal_id.id,
                    'name': 'Payoneer import',
                    'sepa_imported': True,
                })
            if statement.state != 'open':
                statement.write({'state': 'open'})

            statement.line_ids = [(0, 0, line) for line in lines]
            statement.balance_end_real = statement.balance_end
            return statement

    def fix_vals(self, vals):
        good_vals = defaultdict(lambda: [])
        stmtl_ids = self.env['account.bank.statement'].search([
            ('journal_id', '=', self.journal_id.id),
        ]).mapped('line_ids')
        rounding = self.journal_id.currency_id.rounding if self.journal_id.currency_id else 0.01
        for day in sorted(vals):
            stmtl_obj = stmtl_ids.filtered(lambda l: l.date == day)

            # system -- dict(description: amount)
            sys_desc = list(set(stmtl_obj.mapped('name')))
            sys_amounts_by_desc = {desc: sum(stmtl_obj.filtered(lambda l: l.name == desc).mapped('amount')) for desc in sys_desc}

            # file -- dict(description: amount)
            file_amounts_by_desc = defaultdict(lambda: 0.0)
            for line in vals[day]:
                file_amounts_by_desc[line.get('description')] += line.get('amount')

            all_descriptions = list(set(file_amounts_by_desc.keys() + sys_desc))
            for desc in all_descriptions:
                system_amount = sys_amounts_by_desc.get(desc, 0.0)
                file_amount = file_amounts_by_desc.get(desc, 0.0)
                diff = file_amount - system_amount
                if tools.float_is_zero(diff, precision_rounding=rounding):
                    continue

                good_vals[day].append({
                    'status': 'Completed',
                    'currency': self.journal_id.currency_id.name,
                    'amount': diff,
                    'description': desc,
                })

        return good_vals
