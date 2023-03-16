# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.addons.l10n_lt_payroll.model.schedule_template import split_time_range_into_day_and_night_times


class HrEmployeeOvertimeTimeLine(models.Model):
    _inherit = 'hr.employee.overtime.time.line'

    @api.multi
    def get_formatted_work_schedule_times(self, public_holiday_dates=None):
        overtime_marking = self.env.ref('work_schedule.work_schedule_code_VD')
        overtime_nights_marking = self.env.ref('work_schedule.work_schedule_code_VDN', raise_if_not_found=False)
        working_on_free_days_marking = self.env.ref('work_schedule.work_schedule_code_DP')

        if not public_holiday_dates and not isinstance(public_holiday_dates, list):
            public_holiday_dates = self.env['sistema.iseigines'].search([
                ('date', 'in', self.mapped('date'))
            ]).mapped('date')

        res = list()

        for line in self:
            time_from, time_to = line.time_from, line.adjusted_time_to
            times = split_time_range_into_day_and_night_times(time_from, time_to)
            day_times = times.get('day', list())
            night_times = times.get('night', list())
            for day_time in day_times:
                res.append((
                    day_time[0],
                    day_time[1],
                    working_on_free_days_marking.id if line.date in public_holiday_dates else overtime_marking.id
                ))
            for night_time in night_times:
                marking = overtime_nights_marking or overtime_marking
                res.append((
                    night_time[0],
                    night_time[1],
                    marking.id
                ))

        return res


HrEmployeeOvertimeTimeLine()
