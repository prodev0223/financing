# -*- coding: utf-8 -*-

from odoo import api, models


class HrEmployeeCompensation(models.Model):
    _inherit = 'hr.employee.compensation'

    @api.multi
    def action_confirm(self):
        res = super(HrEmployeeCompensation, self).action_confirm()
        for rec in self:
            dates_to_update = rec.mapped('compensation_time_ids.date')
            if not dates_to_update:
                continue

            WorkScheduleDay = self.env['work.schedule.day']
            work_schedule_days = WorkScheduleDay.search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', 'in', dates_to_update),
                ('work_schedule_id', '=', self.env.ref('work_schedule.factual_company_schedule').id),
                ('state', '=', 'draft')
            ])

            days_to_update = WorkScheduleDay
            for date in dates_to_update:
                date_day = work_schedule_days.filtered(lambda day: day.date == date)
                if not date_day:
                    continue
                if len(date_day) > 1:
                    employee_department_day = date_day.filtered(lambda d: d.department_id == d.employee_id.department_id)
                    if employee_department_day:
                        date_day = employee_department_day
                    else:
                        date_day = date_day[0]
                days_to_update |= date_day
            days_to_update.with_context(force_dont_use_planned=True).set_default_schedule_day_values()
        return res


HrEmployeeCompensation()
