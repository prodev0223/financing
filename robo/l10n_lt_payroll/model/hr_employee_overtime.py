# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools
from six import iteritems


class HrEmployeeOvertime(models.Model):
    _name = 'hr.employee.overtime'

    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')], string='State', readonly=True,
                             required=True, default='draft')
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    overtime_compensation = fields.Selection([
        ('monetary', 'Compensated with payment'),
        ('holidays', 'Compensated by adding holiday leaves'),
    ], string='Compensation', required=True, default='monetary')
    overtime_time_line_ids = fields.One2many('hr.employee.overtime.time.line', 'overtime_id', string='Overtime times',
                                             required=True)
    overtime_duration = fields.Float('Overtime duration', compute='_compute_overtime_duration')
    issues = fields.Text(compute='_compute_issues')
    has_issues = fields.Boolean(compute='_compute_has_issues')

    @api.multi
    def name_get(self):
        return [(rec.id, _('{} Overtime').format(rec.employee_id.name)) for rec in self]

    @api.multi
    @api.depends('overtime_time_line_ids.time_from', 'overtime_time_line_ids.time_to')
    def _compute_overtime_duration(self):
        return sum(self.mapped('overtime_time_line_ids.duration'))

    @api.multi
    @api.constrains('overtime_time_line_ids')
    def _check_overtime_time_line_ids(self):
        for rec in self:
            dates_to_check = rec.mapped('overtime_time_line_ids').mapped('date')
            all_overtime_times_for_employee = self.env['hr.employee.overtime.time.line'].search([
                ('overtime_id.employee_id', '=', rec.employee_id.id),
                ('date', 'in', dates_to_check)
            ])
            for date in dates_to_check:
                date_overtime_times = all_overtime_times_for_employee.filtered(
                    lambda overtime_line: overtime_line.date == date
                ).sorted(key=lambda ov: (ov.time_from, ov.time_to))

                if len(date_overtime_times) == 1:
                    continue
                times_from = date_overtime_times[1:].mapped('time_from')
                times_to = date_overtime_times[:-1].mapped('time_to')
                # Normalise times - 0.0 is the same as 24.0
                times_to = [24.0 if tools.float_is_zero(time, precision_digits=2) else time for time in times_to]
                if any(t_from < t_to for t_from, t_to in zip(times_from, times_to)):
                    raise exceptions.UserError(
                        _('Overtime times overlap for date {}. Times can not overlap.').format(date)
                    )

    @api.multi
    @api.depends('overtime_time_line_ids', 'employee_id')
    def _compute_issues(self):
        for rec in self:
            overtime_times = self._convert_overtime_lines_to_overtime_times(rec.overtime_time_line_ids)
            overtime_issues = self._get_overtime_issues(rec.employee_id, overtime_times)
            if overtime_issues:
                rec.issues = '\n'.join(overtime_issues)
            else:
                rec.issues = None

    @api.multi
    @api.depends('overtime_time_line_ids', 'employee_id')
    def _compute_has_issues(self):
        for rec in self:
            rec.has_issues = rec.issues and rec.issues != ''

    @api.model
    def _convert_overtime_lines_to_overtime_times(self, overtime_lines):
        dates = overtime_lines.mapped('date')
        res = dict()
        for date in dates:
            date_lines = overtime_lines.filtered(lambda l: l.date == date)
            res[date] = [(l.time_from, l.time_to) for l in date_lines]
        return res

    @api.model
    def _get_overtime_issues(self, employee, overtime_times):
        """
        Checks given overtime times for specific dates for an employee whether the times should actually be overtime.
        Returns: A list containing issues for the overtime times

        """
        def format_time_to_hours_and_minutes_strings(time):
            hours, minutes = divmod(time * 60.0, 60.0)
            hours, minutes = int(hours), int(minutes)
            hours, minutes = str(hours).zfill(2), str(minutes).zfill(2)
            return hours, minutes

        overtime_dates = overtime_times.keys()

        issues = list()

        if not overtime_times:
            return issues

        min_date, max_date = min(overtime_dates), max(overtime_dates)

        appointments = self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', max_date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min_date)
        ])

        overtime_markings = [self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DP').id,
                             self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VD').id]

        planned_time_ranges = appointments.mapped('schedule_template_id')._get_planned_time_ranges(overtime_dates)

        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '<=', max_date), ('date', '>=', min_date)
        ]).mapped('date')

        template_types_overtime_should_not_be_set_for = ['sumine']

        for date, date_overtime_times in iteritems(overtime_times):
            appointment = appointments.filtered(lambda app: app.date_start <= date and
                                                            (not app.date_end or app.date_end >= date))

            if not appointment:
                issues.append(_('Could not find appointment for date {}').format(date))
                continue

            schedule_template = appointment.schedule_template_id

            if not schedule_template:
                issues.append(
                    _('Employee contract appointment does not have a set schedule template for date {}').format(date)
                )
                continue

            template_type = schedule_template.template_type

            if template_type in template_types_overtime_should_not_be_set_for:
                issues.append(
                    _('Appointment with schedule template type {} for date {} should never have overtime set due '
                      'to the schedule template type').format(template_type, date)
                )
                continue

            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            weekday = date_dt.weekday()
            off_days = schedule_template.off_days()

            if weekday not in off_days and date not in national_holiday_dates:
                for date_overtime_time in date_overtime_times:
                    overtime_from, overtime_to = date_overtime_time[0], date_overtime_time[1]

                    date_planned_time_ranges = planned_time_ranges.get(schedule_template.id, dict()).get(date, list())

                    adjusted_planned_time_ranges = list()
                    for planned_time_range in date_planned_time_ranges:
                        try:
                            marking = planned_time_range[2]
                        except IndexError:
                            marking = None
                        if marking and marking not in overtime_markings:
                            adjusted_planned_time_ranges.append(planned_time_range)

                    is_during_regular_work_time = False

                    for planned_time_range in adjusted_planned_time_ranges:
                        planned_time_from = planned_time_range[0]
                        planned_time_to = planned_time_range[1]
                        if overtime_from <= planned_time_from < overtime_to or \
                                overtime_from < planned_time_to <= overtime_to:
                            is_during_regular_work_time = True

                    if is_during_regular_work_time:
                        overtime_from = format_time_to_hours_and_minutes_strings(overtime_from)
                        overtime_to = format_time_to_hours_and_minutes_strings(overtime_to)

                        issues.append(
                            _('Overtime for date {} overlaps the regular work time for that day. Overtime should not '
                              'be set for the period {}:{}-{}:{}').format(
                                date, overtime_from[0], overtime_from[1], overtime_to[0], overtime_to[1],
                            )
                        )

        overtime_time_limit_check_ranges = set([
            (
                c.work_relation_start_date,
                c.work_relation_end_date,
                c.employee_id.id
            ) for c in appointments.mapped('contract_id')
        ])
        company_id = self.env.user.company_id
        for overtime_time_limit_check_range in overtime_time_limit_check_ranges:
            date_from = overtime_time_limit_check_range[0]
            date_to = overtime_time_limit_check_range[1]
            if not date_from:
                continue
            if not date_to:
                date_to = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            year_from = date_from_dt.year
            year_to = date_to_dt.year
            overtime_lines = self.env['hr.employee.overtime.time.line'].sudo().search([
                ('overtime_id.employee_id', '=', overtime_time_limit_check_range[2]),
                ('date', '<=', date_to),
                ('date', '>=', date_from),
            ])
            if not overtime_lines:
                continue
            while year_from <= year_to:
                year_start_dt = datetime(year_from, 1, 1)
                year_end_dt = year_start_dt + relativedelta(month=12, day=31)
                year_start = year_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                year_end = year_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                year_overtime_lines = overtime_lines.filtered(lambda l: year_start <= l.date <= year_end)
                if not year_overtime_lines:
                    year_from += 1
                    continue
                employee = year_overtime_lines[0].overtime_id.employee_id
                duration = sum(year_overtime_lines.mapped('duration'))
                maximum_overtime_yearly_amount = company_id.with_context(date=year_start).max_overtime_per_year
                if tools.float_compare(duration, maximum_overtime_yearly_amount, precision_digits=2) > 0:
                    issues.append(
                        _('Can not work more than {} hours of overtime per year. Employee {} for period from {} to {} '
                          'works {} hours of overtime').format(
                            maximum_overtime_yearly_amount,
                            employee.name,
                            year_start,
                            year_end,
                            duration
                        )
                    )
                year_from += 1

        return issues

    @api.multi
    def action_draft(self):
        for rec in self.filtered(lambda overtime: overtime.overtime_compensation == 'holidays'):
            rec._create_holiday_fix_adjustment_record(action='subtract')
        self.write({'state': 'draft'})

    @api.multi
    def _create_holiday_fix_adjustment_record(self, action='add'):
        """
        Creates holiday fix adjustment records or modifies them. Adds days based on overtime time lines to
        hr.holidays.fix record or removes them based on the action argument
        @param action: Specifies the action to perform - add or subtract days from hr.holidays.fix adjustment record
        """
        self.ensure_one()
        dates = self.overtime_time_line_ids.mapped('date')
        if not dates:
            return
        appointments = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_start', '<=', max(dates)),
            '|',
            ('date_end', '>=', min(dates)),
            ('date_end', '=', False)
        ])

        holiday_fixes = self.env['hr.holidays.fix']
        if action != 'add':
            holiday_fixes = holiday_fixes.search([
                ('employee_id', '=', self.employee_id.id),
                ('type', '=', 'add'),
                ('date', 'in', dates)
            ])

        for date in dates:
            # Find the appointment for the date
            appointment = appointments.filtered(
                lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date)
            )
            avg_daily_hrs = appointment.schedule_template_id.avg_hours_per_day if appointment else 8.0

            # Get the lines for the date
            lines = self.overtime_time_line_ids.filtered(lambda l: l.date == date)
            time_total = sum(lines.mapped('duration'))

            # Convert line duration to days
            try:
                days_to_adjust = time_total / avg_daily_hrs  # P3:DivOK
            except ZeroDivisionError:
                days_to_adjust = time_total / 8.0  # P3:DivOK

            # Subtract the days rather than add them if the action is not add
            if action != 'add':
                holiday_fix = holiday_fixes.filtered(lambda fix: fix.date == date)
                if not holiday_fix:
                    # Don't adjust the records if no holiday fixes exist for the day
                    days_to_adjust = 0.0
                else:
                    days_to_adjust *= -1

            if not tools.float_is_zero(days_to_adjust, precision_digits=2):
                self.env['hr.holidays.fix'].adjust_fix_days(self.employee_id, date, days_to_adjust)

    @api.multi
    def action_confirm(self):
        for rec in self.filtered(lambda overtime: overtime.overtime_compensation == 'holidays'):
            rec._create_holiday_fix_adjustment_record()
        self.write({'state': 'confirmed'})

    @api.multi
    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise exceptions.ValidationError(_('Overtime records can only be unlinked in draft state'))
        return super(HrEmployeeOvertime, self).unlink()


HrEmployeeOvertime()
