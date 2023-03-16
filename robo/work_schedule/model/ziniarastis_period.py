# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, models, tools


class ZiniarastisPeriod(models.Model):
    _inherit = 'ziniarastis.period'

    @api.multi
    def get_button_statuses(self):
        res = super(ZiniarastisPeriod, self).get_button_statuses()
        is_draft = self.state == 'draft'
        is_busy = self.busy
        res.update({
            'generate_schedule': is_draft and not is_busy,
            'go_to_payroll_schedule': True,
        })
        return res

    @api.multi
    def go_to_payroll_schedule(self):
        action = self.env.ref('work_schedule.action_main_work_schedule_view')
        menu_id = self.env.ref('work_schedule.menu_work_schedule_main').id
        date_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year = date_dt.year
        month = date_dt.month
        res = action.read()[0]
        res['context'] = {
            'robo_menu_name': menu_id,
            'force_back_menu_id': menu_id,
            'robo_front': True,
            'default_year': year,
            'default_month': month,
            'search_default_dept_search': 1,
            'search_add_custom': False
        }
        return res


    @api.multi
    def button_done(self):
        res = super(ZiniarastisPeriod, self).button_done()
        date_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year = date_dt.year
        month = date_dt.month
        factual_work_schedule= self.env.ref('work_schedule.factual_company_schedule')
        schedule_lines = factual_work_schedule.mapped('schedule_line_ids').filtered(lambda l: l.month == month and l.year == year)
        schedule_lines.write({'state': 'done'})
        return res

    @api.one
    def generate_schedule(self):
        self.related_ziniarastis_days.update_schedule_from_ziniarastis()

    @api.multi
    def generate_ziniarasciai(self, contract_ids=None):
        self.ensure_one()
        res = super(ZiniarastisPeriod, self).generate_ziniarasciai(contract_ids)
        if not contract_ids:
            contract_ids = self.env['hr.contract.appointment'].search([
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)]
            ).mapped('contract_id')

        employees = contract_ids.mapped('employee_id')

        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_calc = date_from_dt
        periods = list()
        while date_calc <= date_to_dt:
            periods.append((date_calc.year, date_calc.month))
            date_calc += relativedelta(days=1)

        periods = set(periods)

        for period in periods:
            month = period[1]
            year = period[0]
            existing_line_ids = self.env['work.schedule.line'].search([
                ('employee_id', 'in', employees.mapped('id')),
                ('month', '=', month),
                ('year', '=', year)
            ])
            factual_line_ids = existing_line_ids.filtered(lambda l: l.work_schedule_id.id == factual_work_schedule.id)
            planned_line_ids = existing_line_ids.filtered(lambda l: l.work_schedule_id.id == planned_schedule.id)

            existing_factual_line_employee_ids = factual_line_ids.mapped('employee_id.id')
            employees_to_generate_factual_for = employees.filtered(lambda e: e.id not in existing_factual_line_employee_ids)
            departments = employees_to_generate_factual_for.mapped('department_id')
            default_department = self.env['hr.department'].search([], limit=1)
            for department in departments:
                if not department:
                    department = default_department
                if not department:
                    continue
                department_employees = employees_to_generate_factual_for.filtered(lambda e: e.department_id.id == department.id).mapped('id')
                factual_dep_lines = factual_line_ids.filtered(lambda l: l.department_id.id == department.id)
                planned_dep_lines = planned_line_ids.filtered(lambda l: l.department_id.id == department.id)
                to_create_both_for = []
                copy_from_planned_to_factual = []
                copy_from_factual_to_planned = []
                for empl in department_employees:
                    empl_factual_line = factual_dep_lines.filtered(lambda l: l.employee_id.id == empl)
                    empl_planned_line = planned_dep_lines.filtered(lambda l: l.employee_id.id == empl)
                    if not empl_factual_line and not empl_planned_line:
                        to_create_both_for.append(empl)
                        continue
                    if empl_factual_line and not empl_planned_line:
                        copy_from_factual_to_planned.append(empl)
                        continue
                    if empl_planned_line and not empl_factual_line:
                        copy_from_planned_to_factual.append(empl)
                        continue

                factual_work_schedule.create_empty_schedule(year, month, employee_ids=to_create_both_for, department_ids=[department.id])
                planned_schedule.create_empty_schedule(year, month, employee_ids=to_create_both_for, department_ids=[department.id])

                for empl in copy_from_factual_to_planned:
                    factual_work_schedule.copy_to_schedule(planned_schedule, employee_id=empl, department_id=department.id)

                for empl in copy_from_planned_to_factual:
                    planned_schedule.copy_to_schedule(factual_work_schedule, employee_id=empl, department_id=department.id)
        return res

ZiniarastisPeriod()
