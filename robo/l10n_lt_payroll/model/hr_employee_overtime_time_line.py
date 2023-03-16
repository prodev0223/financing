# -*- coding: utf-8 -*-

from odoo.addons.l10n_lt_payroll.model.schedule_template import split_time_range_into_day_and_night_times, \
    NIGHT_SHIFT_START, NIGHT_SHIFT_END

from odoo import api, fields, models, tools


class HrEmployeeOvertimeTimeLine(models.Model):
    _name = 'hr.employee.overtime.time.line'
    _inherit = ['robo.time.line']

    overtime_id = fields.Many2one('hr.employee.overtime', string='Overtime', required=True, ondelete='cascade')

    @api.multi
    def get_formatted_times(self, public_holiday_dates=None):
        res = list()
        if not self:
            return res

        overtime_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VD')
        overtime_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VDN')
        overtime_on_holidays_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VSS')
        working_on_free_days_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DP')

        if not public_holiday_dates:
            public_holiday_dates = self.env['sistema.iseigines'].search([
                ('date', 'in', self.mapped('date'))
            ]).mapped('date')

        employee_schedule_on_public_holidays = {}
        for line in self:
            time_from, time_to = line.time_from, line.adjusted_time_to
            date = line.date
            employee = line.overtime_id.employee_id
            is_public_holiday = date in public_holiday_dates
            employee_schedule = employee_schedule_on_public_holidays.get(employee.id)
            if not employee_schedule:
                employee_schedule_on_public_holidays[employee.id] = {}
                employee_schedule = {}
            schedule_for_date = employee_schedule.get(date)
            if not schedule_for_date:
                employee_schedule = employee.with_context(date=date).appointment_id.schedule_template_id
                if employee_schedule.template_type not in ['fixed', 'suskaidytos']:
                    # Set all day as schedule time so DP is set rather than overtime on holiday day
                    # 00-24 marks the whole day as work time so DP is set instead of VDS
                    schedule_for_date = [(0.0, 24.0)]
                else:
                    schedule_for_date = employee_schedule.work_times_by_fixed_attendance_line_ids(date=date,
                                                                                                  skip_holidays=False)
                employee_schedule_on_public_holidays[employee.id][date] = schedule_for_date

            # Schedule for date is only retrieved for public holidays
            if schedule_for_date:
                # If an overtime line is for a public holiday then this special case should handle the times that fall
                # under the employee schedule. The overtime lines that are during what's supposed to be regular work
                # hours should be marked as work on public holidays (DP) but any time that is not
                # during the scheduled hours should be as overtime on holidays (VDS)
                # TODO what about overtime on the nights of public holidays?
                schedule_for_date = employee_schedule_on_public_holidays.get(
                    line.overtime_id.employee_id.id, {}
                ).get(line.date, [(0.0, 24.0)])  # 00-24 marks the whole day as work time so DP is set instead of VSS
                schedule_for_date.sort()

                for scheduled_line in schedule_for_date:
                    # Set all time before scheduled line as overtime on holidays
                    temp_time_to = min(time_to, scheduled_line[0])
                    if tools.float_compare(time_from, temp_time_to, precision_digits=2) < 0:
                        marking = overtime_on_holidays_marking if is_public_holiday else overtime_marking
                        res.append((time_from, temp_time_to, marking.id))
                        time_from = temp_time_to
                        if tools.float_compare(time_from, time_to, precision_digits=2) >= 0:
                            break

                    # Set all time during scheduled line as working on free day
                    temp_time_to = min(time_to, scheduled_line[1])
                    if tools.float_compare(time_from, temp_time_to, precision_digits=2) < 0:
                        res.append((time_from, temp_time_to, working_on_free_days_marking.id))
                        time_from = temp_time_to
                        if tools.float_compare(time_from, time_to, precision_digits=2) >= 0:
                            break

                # Set all time after all of the scheduled lines as overtime on holidays
                if tools.float_compare(time_from, time_to, precision_digits=2) < 0:
                    marking = overtime_on_holidays_marking if is_public_holiday else overtime_marking
                    res.append((time_from, time_to, marking.id))
            else:
                times = split_time_range_into_day_and_night_times(time_from, time_to)
                day_times = times.get('day', list())
                night_times = times.get('night', list())
                for day_time in day_times:
                    res.append((
                        day_time[0],
                        day_time[1],
                        working_on_free_days_marking.id
                    ))
                for night_time in night_times:
                    res.append((
                        night_time[0],
                        night_time[1],
                        overtime_nights_marking.id
                    ))

        return res

    @api.multi
    def get_duration_by_time_of_day(self):
        self.ensure_one()
        duration = self.duration
        night_duration = 0.0
        if tools.float_compare(self.time_from, NIGHT_SHIFT_END, precision_digits=2) < 0:
            night_duration += NIGHT_SHIFT_END - self.time_from
        if tools.float_compare(self.time_to, NIGHT_SHIFT_START, precision_digits=2) > 0:
            night_duration += self.time_to - NIGHT_SHIFT_START
        return {
            'day': max(duration - night_duration, 0.0),
            'night': max(night_duration, 0.0)
        }


HrEmployeeOvertimeTimeLine()
