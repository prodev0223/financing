# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES
from odoo.addons.l10n_lt_payroll.model.schedule_tools import find_time_to_set, merge_line_values
from odoo.addons.l10n_lt_payroll.model.schedule_template import split_time_range_into_day_and_night_times, DEFAULT_SCHEDULE_START

from odoo import models, api, tools


class ScheduleTemplate(models.Model):

    _inherit = 'schedule.template'

    @api.multi
    def is_work_day(self, date_str):
        """
        Checks work schedule and its parameters to determine if a date for a specific schedule template is a work day.
        Args:
            date_str (): A string representing a date

        Returns: Boolean - true if date is work day for this schedule template

        """
        self.ensure_one()

        # Native (super) method
        is_work_day = super(ScheduleTemplate, self.with_context(do_not_use_ziniarastis=True)).is_work_day

        # Schedule template might not have an appointment
        if self._context.get('force_use_schedule_template') or not self.appointment_id:
            return is_work_day(date_str)

        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
        work_schedule_lines = self.env['work.schedule.line'].search([
            ('employee_id', '=', self.appointment_id.employee_id.id),
            ('year', '=', date_dt.year),
            ('month', '=', date_dt.month)
        ])

        # If there's no schedule lines use native method
        is_fixed_schedule = self.template_type in ['fixed', 'suskaidytos']
        if not work_schedule_lines or self._context.get('maximum') or \
                (not is_fixed_schedule and self._context.get('calculating_holidays')):
            return is_work_day(date_str)
        elif not any(l.used_as_planned_schedule_in_calculations for l in work_schedule_lines):
            # If we're only trying to get the preliminary holiday duration and there's no planned lines used - we can
            # use the factual schedule
            if self._context.get('calculating_preliminary_holiday_duration') and not is_fixed_schedule:
                first_of_next_month = (datetime.utcnow() + relativedelta(months=1, day=1)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_str >= first_of_next_month:
                    schedule_to_use = planned_work_schedule
                else:
                    schedule_to_use = factual_work_schedule
                work_schedule_lines = work_schedule_lines.filtered(lambda l: l.work_schedule_id == schedule_to_use)
            else:
                return is_work_day(date_str)
        else:
            work_schedule_lines = work_schedule_lines.filtered(lambda l: l.work_schedule_id == planned_work_schedule and
                                                                         l.used_as_planned_schedule_in_calculations)

        # These codes set on work schedule day determine if the day is a work day for that employee
        work_codes = PAYROLL_CODES['REGULAR'] + PAYROLL_CODES['BUDEJIMAS'] + ['DN']
        is_national_holiday = self.env['sistema.iseigines'].search_count([('date', '=', date_str)])
        day_lines = work_schedule_lines.mapped('day_ids').filtered(lambda d: d.date == date_str).mapped('line_ids')
        day_lines = day_lines.filtered(
            lambda l: l.work_schedule_code_id.code in work_codes or
                      (
                          # Count national holiday days as work days if there's extra work time set on planned schedule
                          is_national_holiday and
                          l.work_schedule_code_id.code == 'DP' and
                          l.day_id.work_schedule_line_id.work_schedule_id == planned_work_schedule and
                          l.day_id.work_schedule_line_id.used_as_planned_schedule_in_calculations
                      )
        )
        return bool(day_lines)

    @api.multi
    def get_regular_hours(self, date):
        self.ensure_one()
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        work_schedule_lines = self.env['work.schedule.line'].search([
            ('employee_id', '=', self.appointment_id.employee_id.id),
            ('year', '=', date_dt.year),
            ('month', '=', date_dt.month),
            ('work_schedule_id', '=', planned_work_schedule.id)
        ])
        if self._context.get('maximum') or \
                not any(work_schedule_lines.mapped('used_as_planned_schedule_in_calculations')) or \
                self._context.get('force_get_regular_hours'):
            return super(ScheduleTemplate, self).get_regular_hours(date)

        day_ids = work_schedule_lines.filtered(lambda l: l.used_as_planned_schedule_in_calculations).mapped('day_ids').filtered(lambda d: d.date == date)
        regular_codes = ['FD', 'NT', 'DLS']
        special_codes = ['MP', 'V', 'PN', 'NLL']
        day_lines = day_ids.mapped('line_ids')
        regular_lines = day_lines.filtered(lambda l: l.work_schedule_code_id.code in regular_codes)
        special_lines = day_lines.filtered(lambda l: l.work_schedule_code_id.code in special_codes)
        regular_time = sum(regular_lines.mapped('worked_time_total'))
        special_time = sum(special_lines.mapped('worked_time_total'))
        # If no actual work time defined in planned schedule and only for example downtime time is planned - call super.
        if tools.float_is_zero(regular_time, precision_digits=2) and self._context.get('calculating_work_norm') and \
                not tools.float_is_zero(special_time, precision_digits=2):
            return super(ScheduleTemplate, self).get_regular_hours(date)
        return regular_time

    @api.multi
    def get_working_ranges(self, dates):
        """
            returns dict {date: [(from, to)]}
        """
        self.ensure_one()
        res = {}
        if not dates:
            return res

        if not self.appointment_id:
            return super(ScheduleTemplate, self).get_working_ranges(dates)

        work_schedule_lines = self.env['work.schedule.day'].search([
            ('employee_id', '=', self.appointment_id.employee_id.id),
            ('date', 'in', dates),
            ('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
            ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True)
        ]).mapped('line_ids')

        if not work_schedule_lines:
            return super(ScheduleTemplate, self).get_working_ranges(dates)

        for date in dates:
            res[date] = [(l.time_from, l.time_to) for l in work_schedule_lines.filtered(lambda l: l.date == date)]

        return res

    @api.multi
    def _get_downtime_schedule(self, downtime_object, date, regular_work_times):
        """
        Gets the schedule during downtime for a specific date. Merges regular work time around the downtime schedule.
        Args:
            downtime_object (hr.employee.downtime): The downtime object to get data from
            date (date): The date to get the schedule for
            regular_work_times (dict): A dict containing day lines and night lines that should be worked if the day was
            not during downtime
        Returns: A list containing tuples of the downtime schedule (time_from, time_to, OPTIONAL schedule marking)

        """
        self.ensure_one()

        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Accountant wants changes to take place from July 1st. Also check if schedule is extended.
        if not self.env.user.company_id.sudo().with_context(date=date).extended_schedule or now < '2021-07-01' or \
                date < '2021-07-01':
            return super(ScheduleTemplate, self)._get_downtime_schedule(downtime_object, date, regular_work_times)

        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        start_of_week_dt = date_dt - relativedelta(days=date_dt.weekday())
        end_of_week_dt = start_of_week_dt + relativedelta(days=6)
        start_of_week = start_of_week_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        end_of_week = end_of_week_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        week_planned_days = self.env['work.schedule.day'].search([
            ('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
            ('date', '<=', end_of_week),
            ('date', '>=', start_of_week),
            ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True),
            ('employee_id', '=', self.appointment_id.employee_id.id)
        ])
        if not week_planned_days:
            # No planned time set
            return super(ScheduleTemplate, self)._get_downtime_schedule(downtime_object, date, regular_work_times)

        schedule_nights_marking = self.env.ref('work_schedule.work_schedule_code_DN').id

        regular_work_time_schedule_codes = [
            self.env.ref('work_schedule.work_schedule_code_FD').id,
            self.env.ref('work_schedule.work_schedule_code_DLS').id,
            schedule_nights_marking,
        ]  # TODO should be a setting on work schedule code

        date_planned_day = week_planned_days.filtered(lambda day: day.date == date)
        date_planned_day_lines = date_planned_day.mapped('line_ids').filtered(
            lambda line: line.work_schedule_code_id.id in regular_work_time_schedule_codes and
                         tools.float_compare(line.worked_time_total, 0.0, precision_digits=2) > 0
        )
        week_planned_lines = week_planned_days.mapped('line_ids').filtered(
            lambda line: line.work_schedule_code_id.id in regular_work_time_schedule_codes and
                         tools.float_compare(line.worked_time_total, 0.0, precision_digits=2) > 0
        )

        downtime_schedule = list()

        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')
        regular_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        downtime_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_PN')

        holiday = downtime_object.holiday_id
        if not holiday or not holiday.date_from_date_format <= date <= holiday.date_to_date_format:
            day_lines = regular_work_times.get('day_lines', list())
            night_lines = regular_work_times.get('night_lines', list())
            return day_lines + night_lines  # Return the regular schedule since the day should not be downtime

        day_lines = [
            (
                line.time_from,
                line.time_to,
                line.work_schedule_code_id.tabelio_zymejimas_id.id
            ) for line in date_planned_day_lines if line.work_schedule_code_id.id != schedule_nights_marking
        ]
        night_lines = [
            (
                line.time_from,
                line.time_to,
                line.work_schedule_code_id.tabelio_zymejimas_id.id
            ) for line in date_planned_day_lines if line.work_schedule_code_id.id == schedule_nights_marking
        ]

        if downtime_object.downtime_type == 'full':
            # Full downtime
            come_to_work_schedule = downtime_object.come_to_work_schedule_line_ids  # Get the work schedule
            date_come_to_work_schedule_lines = come_to_work_schedule.filtered(lambda s: s.date == date)
            for line in date_come_to_work_schedule_lines:
                # Split the lines the employee has to work during downtime into day and night lines
                line_split_by_time_of_day = split_time_range_into_day_and_night_times(line.time_from, line.time_to)
                day_lines = line_split_by_time_of_day.get('day_lines', list())
                night_lines = line_split_by_time_of_day.get('night_lines', list())
                # Add lines to downtime schedule as the ones the employee should work
                downtime_schedule += [(l[0], l[1]) for l in day_lines]
                downtime_schedule += [(l[0], l[1], working_nights_marking.id) for l in night_lines]

            day_lines = [(l[0], l[1], downtime_marking.id) for l in day_lines]
            night_lines = [(l[0], l[1], downtime_marking.id) for l in night_lines]

            # Add downtime lines to downtime schedule
            downtime_schedule = merge_line_values(downtime_schedule, day_lines)
            downtime_schedule = merge_line_values(downtime_schedule, night_lines)
        else:
            # Partial downtime
            if not downtime_object.employee_schedule_is_regular:
                downtime_amount = downtime_object.downtime_reduce_in_time  # Downtime per week
                date_planned_work_time = sum(date_planned_day_lines.mapped('worked_time_total'))  # Planned time for day
                week_planned_work_time_before_day = sum(week_planned_lines.filtered(
                    lambda line: line.day_id.date < date
                ).mapped('worked_time_total'))  # Total planned time before this date for this week

                downtime_amount -= week_planned_work_time_before_day  # Days before should already have downtime set
                downtime_amount = max(downtime_amount, 0.0)
                downtime_amount = min(date_planned_work_time, downtime_amount)  # Amount of downtime to set for day

                for day_line in date_planned_day_lines:
                    time_from, time_to = day_line.time_from, day_line.time_to  # Get line times
                    time_total = time_to - time_from  # Total line duration

                    # Maximum downtime to set for this line
                    day_line_downtime_amount = min(time_total, downtime_amount)

                    # Downtime from time_from to max downtime duration
                    downtime_to = min(time_from + day_line_downtime_amount, 24.0)
                    downtime_schedule.append((time_from, downtime_to, downtime_marking.id))  # Add downtime line
                    # If the time of the entire line has not been used - add rest of time as regular work time
                    if tools.float_compare(downtime_to, time_to, precision_digits=2) < 0:
                        downtime_schedule.append((downtime_to, time_to, day_line.tabelio_zymejimas_id.id))

                    # Reduce the amount for next line
                    downtime_amount -= downtime_to - time_from
                    downtime_amount = max(downtime_amount, 0.0)
            else:
                # Get the downtime schedule for date and add it to the downtime schedule list
                downtime_schedule_lines = downtime_object.downtime_schedule_line_ids
                weekday = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
                date_downtime_schedule = downtime_schedule_lines.filtered(lambda s: int(s.weekday) == weekday)
                downtime_schedule += [(l.time_from, l.time_to, regular_work_marking.id) for l in date_downtime_schedule]

                # Fill the rest of the day with downtime work time since the downtime is partial
                day_lines = [(l[0], l[1], downtime_marking.id) for l in day_lines]
                night_lines = [(l[0], l[1], downtime_marking.id) for l in night_lines]

                # When adding regular work time to downtime time - don't set more than the planned regular. This is
                # needed when downtime is set during off hours, before or after the shift, or during the break.

                # Get the regular work time duration for the day
                regular_work_time_day_duration = sum(x[1] - x[0] for x in day_lines)
                regular_work_time_night_duration = sum(x[1] - x[0] for x in night_lines)

                # Get the downtime duration
                downtime_duration = sum(x[1] - x[0] for x in downtime_schedule)

                # Calculate the maximum amount of day time to set
                day_time_to_set = regular_work_time_day_duration - downtime_duration

                # Calculate the maximum amount of night time to set based on how much downtime has been deducted from
                # the day time
                night_time_to_set = 0.0
                if tools.float_compare(day_time_to_set, 0.0, precision_digits=2) < 0:
                    # Only reduce night time if day time to set is negative, meaning that the downtime duration for day
                    # is longer than the regular day time for the day.

                    # Subtracts in all cases since day_time_to_set is always negative
                    night_time_to_set = regular_work_time_night_duration + day_time_to_set

                    day_time_to_set = 0.0  # Don't set any time for day time
                    night_time_to_set = max(0.0, night_time_to_set)

                # Merge downtime with regular times
                if not tools.float_is_zero(day_time_to_set, precision_digits=2):
                    downtime_schedule = merge_line_values(downtime_schedule, day_lines, day_time_to_set)
                if not tools.float_is_zero(night_time_to_set, precision_digits=2):
                    downtime_schedule = merge_line_values(downtime_schedule, night_lines, night_time_to_set)

        downtime_schedule.sort()

        return downtime_schedule
