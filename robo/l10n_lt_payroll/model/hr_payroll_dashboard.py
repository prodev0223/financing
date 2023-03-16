# -*- coding: utf-8 -*-

import json
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import models, api, fields, tools, exceptions, SUPERUSER_ID
from odoo.tools.translate import _
from six import iteritems
import urllib2


def generate_date_list(date_from, date_to):
    if isinstance(date_from, datetime):
        date_from = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    if isinstance(date_to, datetime):
        date_to = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    try:
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
    except ValueError:
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    try:
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
    except ValueError:
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)

    if date_from_dt > date_to_dt:
        raise exceptions.Warning(_('Neteisingos datos.'))
    date = date_from_dt
    dates = []
    while date <= date_to_dt:
        dates.append(date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        date += timedelta(days=1)
    return dates


class HrPayrollDashboard(models.Model):

    _name = 'hr.payroll.dashboard'

    _order = 'date_from'

    name = fields.Char(string='Name', required=True, compute='_compute_name')
    date_from = fields.Date(string='Date from', required=True)
    date_to = fields.Date(string='Date to', required=True)
    exist_payments = fields.Boolean(string='Exist payments', compute='_exist_payments')
    ziniarastis_period_id = fields.Many2one('ziniarastis.period', compute='_compute_ziniarastis_period_id')
    kanban_dashboard_payment_graph = fields.Text(compute='_kanban_dashboard_payment_graph')
    allow_automatic_payroll = fields.Boolean('Leisti skaičiuoti atlyginimus (automatiškai)', compute='_compute_allow_automatic_payroll')
    payroll_id = fields.Many2one('hr.payroll', 'Atlyginimų skaičiavimas', compute='_compute_payroll_id')
    busy = fields.Boolean('Skaičiuojami atlyginimai', compute='_compute_busy')
    show_stage = fields.Boolean('Rodyti skaičiavimo būseną', compute='_compute_show_stage')
    sam_url = fields.Char(readonly=True, inverse='_set_sam_url_date')
    sam_url_date = fields.Datetime('Paskutinė SAM sugeneravimo data', readonly=True)
    show_sam_url = fields.Boolean('Rodyti SAM nuorodą', compute='_compute_show_sam_url')
    allow_perform_sam_action = fields.Boolean('Leisti atlikti SAM veiksmą', compute='_compute_allow_perform_sam_action')
    allow_perform_gpm313_action = fields.Boolean('Leisti atlikti GPM313 formavimo veiksmą', compute='_compute_allow_perform_gpm313_action')
    payroll_history_obj_exists = fields.Boolean('Egzistuoja skaičiavimo istorija', compute='_compute_payroll_history_obj_exists')
    thread_is_active = fields.Boolean('Executing thread is active', compute='_compute_thread_is_active')

    @api.one
    @api.depends('date_from', 'date_to', 'sam_url', 'busy')
    def _compute_payroll_history_obj_exists(self):
        this_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year, month = this_dt.year, this_dt.month
        self.payroll_history_obj_exists = bool(self.env['automatic.payroll.execution.history'].search_count([
            ('year', '=', year),
            ('month', '=', month)
        ]))

    @api.multi
    def action_open_latest_automatic_payroll_history_object(self):
        if not self.payroll_history_obj_exists:
            return True
        else:
            this_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            year, month = this_dt.year, this_dt.month
            history_obj = self.env['automatic.payroll.execution.history'].search([
                ('year', '=', year),
                ('month', '=', month)
            ], order='create_date desc', limit=1)
            res_id = history_obj.id
            return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'automatic.payroll.execution.history',
                'res_id': res_id,
                'view_id': self.env.ref('l10n_lt_payroll.automatic_payroll_execution_history_form').id,
                'type': 'ir.actions.act_window'
            }

    @api.one
    @api.depends('sam_url_date', 'date_from', 'date_to', 'allow_perform_sam_action', 'sam_url')
    def _compute_show_sam_url(self):
        allow_perform_sam_action = self.allow_perform_sam_action

        sam_url_old = False
        if self.sam_url_date:
            last_sam_url_dt = datetime.strptime(self.sam_url_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            now = datetime.utcnow()
            diff = (now - last_sam_url_dt).total_seconds()
            sam_url_old = diff > 10 * 60  # 10 mins

        sam_url_is_set = bool(self.sam_url)

        self.show_sam_url = allow_perform_sam_action and sam_url_is_set and not sam_url_old

    @api.one
    def _set_sam_url_date(self):
        self.sam_url_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.one
    @api.depends('sam_url_date', 'date_from', 'date_to', 'busy')
    def _compute_allow_perform_sam_action(self):
        self.ensure_one()
        payslip_run_closed = bool(self.env['hr.payslip.run'].search_count([
            ('date_start', '=', self.date_from),
            ('date_end', '=', self.date_to),
            ('state', '=', 'close')
        ]))
        is_busy = self.busy
        self.allow_perform_sam_action = not is_busy and self.env.user.is_accountant() and payslip_run_closed

    @api.one
    @api.depends('date_from', 'date_to', 'busy')
    def _compute_allow_perform_gpm313_action(self):
        self.ensure_one()
        payslip_run_closed = bool(self.env['hr.payslip.run'].search_count([
            ('date_start', '=', self.date_from),
            ('date_end', '=', self.date_to),
            ('state', '=', 'close')
        ]))
        gpm_exported = self.env['vmi.document.export'].search_count([('doc_name', '=', 'GPM313.ffdata'),
                                                                     ('state', '=', 'confirmed'),
                                                                     ('file_type', '=', 'ffdata'),
                                                                     ('document_date', '>=', self.date_from),
                                                                     ('document_date', '<=', self.date_to)]) > 0
        if not gpm_exported and not self.busy and self.env.user.is_accountant() and payslip_run_closed:
            self.env.cr.execute("""
                SELECT MAX(F.date_done) as "date"
                FROM account_bank_statement F
                INNER JOIN account_journal J ON (J.id = F.journal_id)                                                            
                WHERE F.company_id = %s
                  AND F.state = 'confirm'
                  AND F.date_done IS NOT NULL
                  AND F.sepa_imported = TRUE
                  AND J.show_on_dashboard = TRUE
                  AND J.currency_id IS NULL
                GROUP BY journal_id
            """, (self.env.user.company_id.id,))
            update_date = self.env.cr.dictfetchall()
            if update_date and update_date[0].get('date'):
                dates = [x['date'] for x in update_date]
                date = min(dates)
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                deadline_dt = datetime.utcnow() - relativedelta(months=1, day=31)
                deadline = deadline_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                self.allow_perform_gpm313_action = date >= deadline
        else:
            self.allow_perform_gpm313_action = False

    @api.multi
    def action_generate_gpm313_url(self):
        self.ensure_one()
        if not self.allow_perform_gpm313_action:
            raise exceptions.ValidationError(_('Negalite atlikti šio veiksmo'))
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.env.user.id == SUPERUSER_ID:
            accountant = self.env.user.company_id.findir
        else:
            accountant = self.env.user
        self.env['hr.payroll'].sudo(accountant.id).generate_gpm313(date_from_dt.month, date_from_dt.year)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.multi
    def action_generate_sam_url(self):
        self.ensure_one()

        allow_perform_sam_action = self.allow_perform_sam_action
        if not allow_perform_sam_action:
            raise exceptions.ValidationError(_('Negalite atlikti šio veiksmo'))

        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year, month = date_from_dt.year, date_from_dt.month
        sam_url = self.env['hr.payroll'].sudo().payroll_executor_send_sam(month, year)
        if sam_url:
            sam_url = urllib2.unquote(sam_url)
        self.sam_url = sam_url


    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        self.name = '%s - %s' % (self.date_from or '', self.date_to or '')

    @api.one
    @api.depends('payroll_id')
    def _compute_show_stage(self):
        if self.payroll_id and self.payroll_id.busy and self.payroll_id.partial_calculations_running and self.payroll_id.stage:
            self.show_stage = True
        else:
            self.show_stage = False

    @api.multi
    def name_get(self):
        return [(rec.id, '%s - %s' % (rec.date_from, rec.date_to)) for rec in self]

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_ziniarastis_period_id(self):
        if not self.date_from or not self.date_to:
            self.ziniarastis_period_id = False
        ziniarastis_period = self.env['ziniarastis.period'].search([('date_from', '=', self.date_from),
                                                                    ('date_to', '=', self.date_to)], limit=1)
        self.ziniarastis_period_id = ziniarastis_period.id or False

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_allow_automatic_payroll(self):
        payslip_run_id = self.env['hr.payslip.run'].search([
            ('date_start', '=', self.date_from),
            ('date_end', '=', self.date_to),
        ], limit=1)
        self.allow_automatic_payroll = not self.payroll_id.busy and (not payslip_run_id or payslip_run_id.state != 'close')

    @api.multi
    @api.depends('date_from', 'date_to')
    def _compute_payroll_id(self):
        HrPayroll = self.env['hr.payroll']
        payrolls = HrPayroll.search([
            ('date_from', '>=', min(self.mapped('date_from'))),
            ('date_to', '<=', max(self.mapped('date_to')))
        ])
        for rec in self:
            payroll = payrolls.filtered(lambda payroll: payroll.date_from == rec.date_from and
                                                         payroll.date_to == rec.date_to)
            payroll = payroll and payroll[0]
            if not payroll:
                date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                payroll = HrPayroll.create({
                    'year': date_from_dt.year,
                    'month': date_from_dt.month
                })
            rec.payroll_id = payroll

    @api.multi
    @api.depends('date_from', 'date_to')
    def _compute_busy(self):
        for rec in self:
            rec.busy = rec.payroll_id and rec.payroll_id.busy

    @api.multi
    def execute_automatic_payroll_button(self):
        self.ensure_one()
        if self.busy:
            raise exceptions.ValidationError(_('Atlyginimai jau skaičiuojami'))
        else:
            self.payroll_id.launch_automatic_payroll()

    @api.multi
    @api.depends('date_from', 'date_to')
    def _compute_thread_is_active(self):
        for rec in self.filtered(lambda dashboard: dashboard.payroll_id):
            rec.thread_is_active = rec.payroll_id.thread_is_active

    @api.multi
    def reset_automatic_payroll(self):
        self.ensure_one()
        self.payroll_id.stop_automatic_payroll()

    @api.one
    def _kanban_dashboard_payment_graph(self):
        self.kanban_dashboard_payment_graph = json.dumps(self.get_payment_graph_datas())

    @api.multi
    def open_payslips(self):
        payslip_runs = self.env['hr.payslip.run'].search([('date_start', '=', self.date_from),
                                                         ('date_end', '=', self.date_to)])
        action = self.env.ref('l10n_lt_payroll.action_darbo_avansai_run')
        res = {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'res_model': 'hr.payslip.run',
            'view_id': False,
        }
        if len(payslip_runs) == 1:
            res.update({
                'view_mode': 'form',
                'res_id': payslip_runs.id,
            })
        else:
            res.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', payslip_runs.ids)],
            })
        return res

    @api.multi
    def create_advance_payments(self):
        self.ensure_one()
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year, month = date_from_dt.year, date_from_dt.month
        day = self.env.user.company_id.advance_payment_day
        try:
            op_date = datetime(year, month, day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            op_date = datetime(year, month, 20).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        advance_payment = self.env['avanasai.run'].create({'date_from': self.date_from,
                                                           'date_to': self.date_to,
                                                           'operation_date': op_date})
        action = self.env.ref('l10n_lt_payroll.action_darbo_avansai_run')
        return {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'avansai.run',
            'view_id': False,
            'res_id': advance_payment.id,
        }

    @api.multi
    def open_advance_payments(self):
        self.ensure_one()
        advance_runs = self.env['avansai.run'].search([('date_from', '>=', self.date_from),
                                                       ('date_to', '<=', self.date_to)])
        action = self.env.ref('l10n_lt_payroll.action_darbo_avansai_run')
        res = {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'res_model': 'avansai.run',
            'view_id': False,
        }

        if len(advance_runs) == 1:
            res.update({
                'view_mode': 'form',
                'res_id': advance_runs.id,
            })
        elif len(advance_runs) > 1:
            res.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', advance_runs.ids)],
            })
        else:
            advance_payments = self.env['darbo.avansas'].search([('date_from', '>=', self.date_from),
                                                                 ('date_to', '<=', self.date_to)])
            action = self.env.ref('l10n_lt_payroll.action_darbo_avansas')
            res = {
                'id': action.id,
                'name': action.name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_id': False,
            }
            if len(advance_payments) == 1:
                res.update({
                    'view_mode': 'form',
                    'res_model': 'darbo.avansas',
                    'res_id': advance_payments.id,
                })
            elif len(advance_payments) > 1:
                res.update({
                    'view_mode': 'tree,form',
                    'res_model': 'avansai.run',
                    'domain': [('id', 'in', advance_payments.ids)],
                })
            else:
                raise exceptions.UserError(_('Nėra suformuotų avansų'))
        return res

    @api.multi
    def open_other_payments(self):
        self.ensure_one()
        action = self.env.ref('l10n_lt_payroll.action_holiday_pay')
        return {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.employee.payment',
            'view_id': False,
            'domain': [('date_from', '<=', self.date_to), ('date_to', '>=', self.date_from)],
        }

    @api.multi
    def open_ziniarastis(self):
        res_id = self.ziniarastis_period_id.id
        if not res_id:
            vals = {'date_from': self.date_from,
                    'date_to': self.date_to}
            ziniarastis = self.env['ziniarastis.period'].create(vals)
            self.payroll_id.write({
                'busy': True,
                'partial_calculations_running': True,
                'stage': 'undefined',
            })
            self._cr.commit()
            ziniarastis.generate_ziniarasciai_background()
            return self.env.ref('l10n_lt_payroll.open_payroll_dashboard_kanban').read()[0]
        action = self.env.ref('l10n_lt_payroll.action_ziniarastis')
        view_id = self.env.ref('l10n_lt_payroll.ziniarastis_period_form')
        menu_id = self.env.ref('l10n_lt_payroll.meniu_ziniarastis_period').id
        all_ziniarastis_ids = self.env['ziniarastis.period'].search([], order='date_from asc').mapped('id')
        current_index = all_ziniarastis_ids.index(res_id)
        return {
            'id': action.id,
            'name': action.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'ziniarastis',
            'views': [[view_id.id, 'ziniarastis']],
            'res_model': 'ziniarastis.period',
            'view_id': view_id.id,
            'res_id': res_id,
            'context': {
                'force_back_menu_id': menu_id,
                'dataset_ids': all_ziniarastis_ids,
                'dataset_index': current_index
            }
        }

    @api.multi
    def open_bank_statements(self):
        bank_statements = self.env['account.bank.statement'].search([('date', '>=', self.date_from),
                                                                     ('date', '<=', self.date_to),
                                                                     ('sepa_imported', '=', False)])
        bank_statement_ids = bank_statements.filtered(lambda r: not r.all_lines_reconciled).ids

        return {
            'name': _('Bank statements'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.bank.statement',
            'view_id': False,
            'domain': [('id', 'in', bank_statement_ids)],
        }

    @api.multi
    @api.constrains('date_from', 'date_to')
    def constrain_dates(self):
        for rec in self:
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt.day != 1:
                raise exceptions.ValidationError(_('Pradžios data turi būti mėnesio pirmoji diena.'))
            if (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT) != rec.date_to:
                raise exceptions.ValidationError(
                    _('Pradžios ir pabaigos datos turi sutapti su mėnesio pradžia ir pabaiga.')
                )

    @api.model
    def generate_dashboards(self):
        cur_date = datetime.utcnow()
        next_month_date_from = (cur_date + relativedelta(day=1, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        next_month_date_to = (cur_date + relativedelta(day=31, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        next_month_values = {'date_from': next_month_date_from,
                             'date_to': next_month_date_to}
        cur_month_date_from = (cur_date + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        cur_month_date_to = (cur_date + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        cur_month_values = {'date_from': cur_month_date_from,
                            'date_to': cur_month_date_to}
        prev_month_date_from = (cur_date + relativedelta(day=1, months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        prev_month_date_to = (cur_date + relativedelta(day=31, months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        prev_month_values = {'date_from': prev_month_date_from,
                             'date_to': prev_month_date_to}

        self.env['hr.payroll.dashboard'].search([]).unlink()
        self.env['hr.payroll.dashboard'].create(next_month_values)
        self.env['hr.payroll.dashboard'].create(cur_month_values)
        self.env['hr.payroll.dashboard'].create(prev_month_values)

    @api.one
    def _exist_payments(self):
        company = self.env.user.company_id
        accounts = company.saskaita_sodra | company.saskaita_gpm | company.saskaita_kreditas
        payments = self.env['account.move.line'].search_count([('account_id', 'in', accounts.ids),
                                                               ('date_maturity', '>=', self.date_from),
                                                               ('date_maturity', '<=', self.date_to),
                                                               ('amount_residual', '<', -1),
                                                               ('move_id.state', '=', 'posted'),
                                                               ])
        self.exist_payments = bool(payments)

    @api.multi
    def get_payment_graph_datas(self):
        company_id = self.env.user.company_id
        accounts = {'SD': company_id.saskaita_sodra.id,
                    'GPM': company_id.saskaita_gpm.id,
                    'NETO': company_id.saskaita_kreditas.id,
                    }
        unused_keys = []
        for k, v in iteritems(accounts):
            if not v:
                unused_keys.append(k)
        for k in unused_keys:
            accounts.pop(k)
        colors = {'SD': 'blue', 'GPM': 'red', 'NETO': 'green'}
        all_payments = self.env['account.move.line'].search([('account_id', 'in', accounts.values()),
                                                             ('date_maturity', '>=', self.date_from),
                                                             ('date_maturity', '<=', self.date_to),
                                                             ('amount_residual', '<', 0),
                                                             ('move_id.state', '=', 'posted'),
                                                             ])
        # payments_to_make = all_payments.filtered(lambda r: not r.reconciled)

        full_data = []
        date_keys = generate_date_list(self.date_from, self.date_to)
        for account_name, account_id in iteritems(accounts):
            related_payments = all_payments.filtered(lambda r: r.account_id.id == account_id)
            # related_made_payments = payments_to_make.filtered(lambda r: r.account_id.id == account_id)
            related_payments_by_date = {}
            related_made_payments_by_date = {}
            for date in date_keys:
                related_payments_by_date[date] = 0
                related_made_payments_by_date[date] = 0
            for rel_pay in related_payments:
                date = rel_pay.date_maturity
                # amount = rel_pay.credit - rel_pay.debit
                amount = -rel_pay.amount_residual
                if date in related_payments_by_date:
                    related_payments_by_date[date] += amount
            for date in related_payments_by_date.keys():  # small amounts are there probably because of rounding of income tax
                if tools.float_compare(related_payments_by_date[date], 10, precision_digits=0) <= 0:
                    related_payments_by_date[date] = 0.0
            payment_data = {'key': account_name, 'values': [{'y': related_payments_by_date[date], 'color': colors.get(account_name, 'black'),
                                                      'label': str(int(date[-2:]))} for date in date_keys]}
            full_data.append(payment_data)
        return {'data': full_data, 'options': {'show_legend': 1, 'show_controls': 0}}


HrPayrollDashboard()
