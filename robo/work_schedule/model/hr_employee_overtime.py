# -*- coding: utf-8 -*-

from odoo.addons.l10n_lt_payroll.model.schedule_tools import merge_line_values

from odoo import api, models, tools
from six import iteritems


class HrEmployeeOvertime(models.Model):
    _inherit = 'hr.employee.overtime'

    @api.multi
    def action_draft(self):
        overtime_marking = self.env.ref('work_schedule.work_schedule_code_VD')
        overtime_night_marking = self.env.ref('work_schedule.work_schedule_code_VDN', raise_if_not_found=False)
        working_on_free_days_marking = self.env.ref('work_schedule.work_schedule_code_DP')
        overtime_markings = [overtime_marking.id, working_on_free_days_marking.id]
        if overtime_night_marking:
            overtime_markings.append(overtime_night_marking.id)
        affected_work_schedule_days = self._get_affected_work_schedule_days()
        for rec in self:
            overtime_lines = rec.overtime_time_line_ids
            dates = overtime_lines.mapped('date')
            affected_days = affected_work_schedule_days.filtered(
                lambda d: d.employee_id == rec.employee_id and d.date in dates
            )
            for overtime_line in overtime_lines:
                date = overtime_line.date
                date_days = affected_days.filtered(lambda d: d.date == date)
                lines = date_days.mapped('line_ids')
                affected_lines = lines.filtered(lambda l: l.work_schedule_code_id.id in overtime_markings and
                                                          l.time_from == overtime_line.time_from and
                                                          l.time_to == overtime_line.time_to)
                affected_lines.sudo().with_context(allow_delete_special=True).unlink()

        super(HrEmployeeOvertime, self).action_draft()

    @api.multi
    def action_confirm(self):
        affected_work_schedule_days = self._get_affected_work_schedule_days()

        dates = self.mapped('overtime_time_line_ids.date')
        public_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', 'in', dates)
        ]).mapped('date')

        for rec in self:
            overtime_lines = rec.overtime_time_line_ids
            employee = rec.employee_id
            main_employee_department = employee.department_id
            dates = overtime_lines.mapped('date')
            affected_days = affected_work_schedule_days.filtered(
                lambda d: d.employee_id == rec.employee_id and d.date in dates)
            for date in dates:
                date_overtime_lines = overtime_lines.filtered(lambda l: l.date == date)
                overtime_times = date_overtime_lines.get_formatted_work_schedule_times(public_holiday_dates)

                date_days = affected_days.filtered(lambda d: d.date == date)
                if not date_days:
                    continue

                if main_employee_department:
                    day_to_set_overtime_in = date_days.filtered(lambda d: d.department_id == main_employee_department)
                else:
                    day_to_set_overtime_in = date_days[0]

                current_day_lines = day_to_set_overtime_in.line_ids
                current_day_times = [(l.time_from, l.time_to, l.work_schedule_code_id.id) for l in current_day_lines]

                day_to_set_overtime_in_schedule = merge_line_values(overtime_times, current_day_times)

                date_work_schedule_line_values = {
                    day_to_set_overtime_in.id: day_to_set_overtime_in_schedule
                }

                other_days = date_days.filtered(lambda d: d != day_to_set_overtime_in)
                for overtime_time in overtime_times:
                    overtime_from, overtime_to = overtime_time[0], overtime_time[1]
                    for day in other_days:
                        lines = day.line_ids
                        overlapping_lines = lines.filtered(
                            lambda l: l.time_to >= overtime_from and l.time_from <= overtime_to
                        )
                        if not overlapping_lines:
                            continue
                        day_times_to_set = [
                            (l.time_from, l.time_to, l.work_schedule_code_id.id)
                            for l in lines if l not in overlapping_lines
                        ]
                        for line in overlapping_lines:
                            time_from, time_to = line.time_from, line.time_to
                            if time_from < overtime_to:
                                time_to = overtime_from
                            else:
                                time_from = overtime_to
                            if time_from >= time_to:
                                continue
                            else:
                                day_times_to_set.append((time_from, time_to, line.work_schedule_code_id.id))
                        date_work_schedule_line_values[day.id] = day_times_to_set

                day_ids_to_update = date_work_schedule_line_values.keys()
                days = self.env['work.schedule.day'].browse(day_ids_to_update)
                days.mapped('line_ids').with_context(allow_delete_special=True).unlink()
                for day_id, lines in iteritems(date_work_schedule_line_values):
                    day = self.env['work.schedule.day'].browse(day_id)
                    line_values = [
                        (0, 0, {
                            'day_id': day.id,
                            'time_from': line[0],
                            'time_to': line[1],
                            'work_schedule_code_id': line[2],
                            'prevent_deletion': any(
                                tools.float_compare(t[0], line[0], precision_digits=2) == 0 and
                                tools.float_compare(t[1], line[1], precision_digits=2) == 0 and
                                t[2] == line[2] for t in overtime_times
                            )
                        }) for line in lines
                    ]
                    day.line_ids.with_context(allow_delete_special=True).unlink()
                    day.write({'line_ids': line_values})

        super(HrEmployeeOvertime, self).action_confirm()

    @api.multi
    def _get_affected_work_schedule_days(self):
        overtime_lines = self.mapped('overtime_time_line_ids')
        employees = overtime_lines.mapped('overtime_id.employee_id')
        dates = overtime_lines.mapped('date')
        work_schedule_days = self.env['work.schedule.day'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date', 'in', dates),
            ('work_schedule_id', '=', self.env.ref('work_schedule.factual_company_schedule').id),
            ('state', '=', 'draft')
        ])
        return work_schedule_days


HrEmployeeOvertime()
