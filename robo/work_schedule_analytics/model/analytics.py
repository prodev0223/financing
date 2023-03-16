# -*- coding: utf-8 -*-
from __future__ import division
from odoo import api, fields, models, exceptions
from odoo.tools import float_is_zero
from odoo.tools.translate import _
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    analytic_type = fields.Selection(selection_add=[('payroll_schedule', 'Pagal grafiko padalinius')])

    @api.multi
    def get_amounts_by_analytic_acc_id(self):
        line_codes_for_analytics = PAYROLL_CODES['NORMAL'] + PAYROLL_CODES['SUMINE']
        self.ensure_one()
        res = amounts_by_analytic_account_id = {}
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        if self.analytic_type != 'payroll_schedule':
            res = super(HrPayslip, self).get_amounts_by_analytic_acc_id()
        else:
            days = self.env['work.schedule.day'].search([('employee_id', '=', self.employee_id.id),
                                                         ('date', '>=', self.date_from),
                                                         ('date', '<=', self.date_to),
                                                         ('work_schedule_id', '=', factual_work_schedule.id)])
            departments = days.mapped('department_id')
            main_department = self.employee_id.department_id

            total_qty = 0.0

            for department in departments:
                department_account = department.analytic_account_id

                if not department_account:
                    raise exceptions.UserError(_(
                        "Neįmanoma paskaičiuoti analitikos, nes nenustatyta padalinio %s analitinė sąskaita.\nKoreguokite padalinio nustatymus pridėdami sąskaitas arba pakeiskite DU analitikos tipą.") % (
                                                   department.name))

                department_days = days.filtered(lambda r: r['department_id']['id'] == department.id)
                department_day_lines = department_days.mapped('line_ids')
                if len(department_day_lines) != 0:
                    department_time_sum = sum(department_day_lines.filtered(
                        lambda l: l['tabelio_zymejimas_id']['code'] in line_codes_for_analytics).mapped(
                        'worked_time_total')) if line_codes_for_analytics else sum(
                        department_day_lines.mapped('worked_time_total'))
                else:
                    department_time_sum = 0.0
                total_qty += department_time_sum

                if department_account.id not in amounts_by_analytic_account_id:
                    amounts_by_analytic_account_id[department_account.id] = department_time_sum
                else:
                    amounts_by_analytic_account_id[department_account.id] += department_time_sum

            # Previously worked time totals were written in the amount_by_analytic_account_id and we need percentages of the total worked hours.

            if not float_is_zero(total_qty, precision_digits=2):
                for account in amounts_by_analytic_account_id:
                    amounts_by_analytic_account_id[account] = min(
                        (amounts_by_analytic_account_id[account] / total_qty * 100.0), 100.0)  # P3:DivOK
            else:
                for account in amounts_by_analytic_account_id:
                    amounts_by_analytic_account_id[account] = 0.0
                if main_department.analytic_account_id:
                    amounts_by_analytic_account_id[main_department.analytic_account_id.id] = 100.0

        return res


HrPayslip()


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    analytic_type = fields.Selection(selection_add=[('payroll_schedule', 'Pagal grafiko padalinius')])

    @api.multi
    def _check_payroll_analytics_are_enabled_when_forced(self):
        require_payroll_analytics = self.sudo().env.user.company_id.required_du_analytic
        if not require_payroll_analytics:
            return
        other_types_of_analytics = self.filtered(lambda employee: employee.analytic_type != 'payroll_schedule')
        super(HrEmployee, other_types_of_analytics)._check_payroll_analytics_are_enabled_when_forced()


HrEmployee()


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    analytic_account_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita', required=False)


HrDepartment()
