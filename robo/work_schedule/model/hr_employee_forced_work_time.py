# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools


class HrEmployeeForcedWorkTime(models.Model):
    _inherit = 'hr.employee.forced.work.time'

    time_from = fields.Float(inverse='_update_work_schedule_values')
    time_to = fields.Float(inverse='_update_work_schedule_values')
    work_schedule_day_line_id = fields.Many2one('work.schedule.day.line', 'Related work schedule line')

    @api.multi
    def _update_work_schedule_values(self):
        self.remove_related_work_schedule_lines()
        # Find related work schedule days to pass to methods later instead of executing search query in each method
        related_work_schedule_days = self.find_related_work_schedule_days()
        self.backup_work_schedule(related_days=related_work_schedule_days)
        self.create_work_schedule_lines(related_days=related_work_schedule_days)

    @api.multi
    def remove_related_work_schedule_lines(self):
        self.mapped('work_schedule_day_line_id').exists().with_context(allow_delete_special=True).unlink()

    @api.multi
    def backup_work_schedule(self, related_days=None):
        if not related_days:
            related_days = self.find_related_work_schedule_days()
        related_days.filtered(lambda d: d.line_ids).backup_days(raise_error=False)

    @api.multi
    def create_work_schedule_lines(self, related_days=None):
        def times_overlap(start_time_1, end_time_1, start_time_2, end_time_2):
            return tools.float_compare(start_time_1, end_time_2, precision_digits=2) < 0 and \
                   tools.float_compare(start_time_2, end_time_1, precision_digits=2) < 0

        if not related_days:
            related_days = self.find_related_work_schedule_days()

        related_work_schedule_markings = self.env['work.schedule.codes'].search([
            ('tabelio_zymejimas_id', 'in', self.mapped('marking_id').ids)
        ])

        for forced_time in self:
            date_related_days = related_days.filtered(
                lambda d: d.employee_id == forced_time.employee_id and d.date == forced_time.date
            )
            if not date_related_days:
                continue  # Line should be created when day is created
            overlapping_lines = date_related_days.line_ids.filtered(
                lambda l: times_overlap(l.time_from, l.time_to, forced_time.time_from, forced_time.time_to)
            )
            if any(l.holiday_id or l.prevent_deletion or l.matched_holiday_id for l in overlapping_lines):
                continue  # Day has confirmed holidays, do nothing

            # Delete overlapping lines
            overlapping_lines.unlink()

            if len(date_related_days) > 1:
                related_day = date_related_days.filtered(
                    lambda d: d.department_id == forced_time.employee_id.department_id
                ) or date_related_days[0]
            else:
                related_day = date_related_days

            try:
                # Create a work schedule line based on this forced work time
                work_schedule_code = related_work_schedule_markings.filtered(
                    lambda m: m.tabelio_zymejimas_id == forced_time.marking_id
                )
                if not work_schedule_code:
                    continue
                work_schedule_line = self.env['work.schedule.day.line'].create({
                    'work_schedule_code_id': work_schedule_code.id,
                    'time_from': forced_time.time_from,
                    'time_to': forced_time.time_to,
                    'day_id': related_day.id,
                    'prevent_deletion': True
                })
                forced_time.write({'work_schedule_day_line_id': work_schedule_line.id})
            except:
                pass

    @api.multi
    def _create_work_schedule_values(self):
        days = self.find_related_work_schedule_days().filtered(lambda d: d.line_ids)
        days.backup_days(raise_error=False)
        days.mapped('line_ids').sudo().with_context(allow_delete_special=True).unlink()
        days.set_default_schedule_day_values()

    @api.multi
    def _restore_work_schedule(self):
        # Find related work schedule days
        dates = self.mapped('date')
        employees = self.mapped('employee_id')
        days = self.env['work.schedule.day'].search([
            ('employee_id', 'in', employees.ids),
            ('date', 'in', dates),
            ('work_schedule_id', '=', self.env.ref('work_schedule.factual_company_schedule').id)
        ])

        # Delete all lines and restore schedule from backup
        days.mapped('line_ids').sudo().unlink()
        days.restore_data_from_backup_schedule(raise_error=False, force_restore=True)

    @api.multi
    def find_related_work_schedule_days(self):
        data = list(set([(x.employee_id.id, x.date) for x in self]))
        factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')

        # Build a domain to find affected work schedule days for each date and each employee
        domain = []
        data_length = len(data)
        for i in range(0, data_length):
            if (i != 0 or data_length > 1) and i != data_length - 1:
                domain.append('|')
            iterator_data = data[i]
            schedule_to_be_used = planned_schedule if \
                datetime.strptime(iterator_data[1], tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1) > \
                datetime.utcnow() + relativedelta(day=1) else factual_schedule
            domain += [
                '&',
                ('employee_id', '=', iterator_data[0]),
                '&',
                ('date', '=', iterator_data[1]),
                ('work_schedule_id', '=', schedule_to_be_used.id)
            ]
        return self.env['work.schedule.day'].search(domain)

    @api.multi
    def unlink(self):
        self.remove_related_work_schedule_lines()
        return super(HrEmployeeForcedWorkTime, self).unlink()


HrEmployeeForcedWorkTime()
