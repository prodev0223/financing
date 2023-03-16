# -*- encoding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, _, exceptions, tools
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES


CODES_HOLIDAYS = ['A', 'G', 'KA', 'KR', 'M', 'MP', 'NLL', 'MA', 'N', 'NA', 'ND', 'P', 'PV', 'TA', 'V']
CODES_ABSENCE = ['D', 'KM', 'KT', 'L', 'NN', 'NP', 'NS', 'PB', 'PK', 'PN', 'ST', 'VV']


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def employee_work_norm(self, calc_date_from=False, calc_date_to=False, employee=False, contract=False,
                           appointment=False, calculate_for_six_day_week=False, skip_leaves=False):
        # Determine if leaves should be skipped
        if not (employee or contract or appointment):
            skip_leaves = False

        # Work schedule does not play a role if leaves are not skipped.
        if not skip_leaves:
            return super(HrEmployee, self).employee_work_norm(calc_date_from, calc_date_to, employee, contract,
                                                              appointment, calculate_for_six_day_week, skip_leaves)

        initial_contract = contract  # Store value of provided contract

        # Determine period
        date_from = calc_date_from
        date_to = calc_date_to
        if appointment:
            date_from = appointment.date_start if appointment.date_start > date_from else date_from
            if appointment.date_end and (not date_to or date_to > appointment.date_end):
                date_to = appointment.date_end
            contract = appointment.contract_id
        elif contract:
            date_from = contract.date_start if contract.date_start > date_from else date_from
            if contract.date_end and (not date_to or date_to > contract.date_end):
                date_to = contract.date_end

        # Force use maximum
        if self._context.get('maximum'):
            if not appointment:
                raise exceptions.UserError(_('Negalima nustatyti maksimalaus darbo laiko.'))
            date_from = calc_date_from
            date_to = calc_date_to

        # Check dates have been determined
        if not date_from:
            raise exceptions.UserError(_('Negalima nustatyti datos, nuo kurios skaičiuoti darbo normą'))
        if not date_to:
            raise exceptions.UserError(_('Negalima nustatyti datos, iki kurios skaičiuoti darbo normą'))

        # Find appointments for period
        if employee and not contract:
            contracts = self.sudo().env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '>=', date_from),
                ('date_end', '=', False)
            ])
        appointments = False
        if appointment:
            appointments = appointment
        elif contract:
            appointments = contract.appointment_ids.filtered(
                lambda app: app.date_start <= date_to and (not app.date_end or app.date_end >= date_from)
            )
        elif employee:
            appointments = contracts.mapped('appointment_ids').filtered(
                lambda app: app.date_start <= date_to and (not app.date_end or app.date_end >= date_from)
            )

        # Find related work schedule objects - planned days and (work schedule) holidays
        work_schedule_days = self.env['work.schedule.day']
        if appointments:
            work_schedule_days = self.env['work.schedule.day'].search([
                ('employee_id', 'in', appointments.mapped('employee_id.id')),
                ('date', '<=', date_to),
                ('date', '>=', date_from)
            ])
        planned_schedule_days = work_schedule_days.filtered(
            lambda d: d.work_schedule_id.schedule_type == 'planned' and
                      d.work_schedule_line_id.used_as_planned_schedule_in_calculations
        )
        if not planned_schedule_days:
            # No planned days for given employee so we should revert to the work norm based on ziniarastis.
            return super(HrEmployee, self).employee_work_norm(calc_date_from, calc_date_to, employee, initial_contract,
                                                              appointment, calculate_for_six_day_week, skip_leaves)

        # Find work schedule holidays that are not business trips
        business_trip_status = self.env.ref('hr_holidays.holiday_status_K')
        holidays = work_schedule_days.mapped('holiday_ids').filtered(
            lambda h: h.holiday_status_id != business_trip_status
        )

        # We should only calculate the work norm during the holidays and add that to the regular work norm
        # Force don't skip leaves here because we want the full work norm and later we'll subtract leaves from work
        # schedule by calculating the planned work time for each day
        work_norm = super(HrEmployee, self).employee_work_norm(calc_date_from, calc_date_to, employee, contract,
                                                               appointment, calculate_for_six_day_week,
                                                               skip_leaves=False)
        # Nothing to do
        if not holidays:
            return work_norm

        # List of holidays that shorten the work norm by the planned time, provided by accountant.
        use_planned_schedule_holiday_statuses = [
            self.env.ref('hr_holidays.holiday_status_sl'),
            self.env.ref('hr_holidays.holiday_status_NS'),
            self.env.ref('hr_holidays.holiday_status_SŽ'),
            self.env.ref('hr_holidays.holiday_status_KV'),
            self.env.ref('hr_holidays.holiday_status_KVN'),
            self.env.ref('hr_holidays.holiday_status_VV'),
            self.env.ref('hr_holidays.holiday_status_PK'),
            self.env.ref('hr_holidays.holiday_status_ND'),
            self.env.ref('hr_holidays.holiday_status_NP'),
            self.env.ref('hr_holidays.holiday_status_NN'),
            self.env.ref('hr_holidays.holiday_status_ST'),
            # self.env.ref('hr_holidays.holiday_status_VP'),  # Should use default work norm based on post
            self.env.ref('hr_holidays.holiday_status_D'),
            self.env.ref('hr_holidays.holiday_status_PP')
        ]

        # If no planned time is set for these codes, instead of using work norm - use factual set time
        use_set_hours_statuses = [
            self.env.ref('hr_holidays.holiday_status_MP'),
            self.env.ref('hr_holidays.holiday_status_NLL'),
            self.env.ref('hr_holidays.holiday_status_V'),
            self.env.ref('hr_holidays.holiday_status_PB'),
            self.env.ref('hr_holidays.holiday_status_PN')
        ]

        # Find ziniarastis data
        ziniarastis_period_lines = self.env['ziniarastis.period.line'].search([
            ('contract_id', 'in', appointments.mapped('contract_id').ids),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from)
        ])
        ziniarastis_days = ziniarastis_period_lines.mapped('ziniarastis_day_ids')

        # Codes that determine work norm
        CODES_TO_USE = PAYROLL_CODES['NORMAL'] + PAYROLL_CODES['OUT_OF_OFFICE'] + PAYROLL_CODES['UNPAID_OUT_OF_OFFICE']

        # Set default durations used by leaves
        leave_hours, leave_days = 0.0, 0

        # Find related work schedule codes
        related_work_schedule_codes = self.env['work.schedule.codes'].search([
            ('tabelio_zymejimas_id', 'in', holidays.mapped('holiday_status_id.tabelio_zymejimas_id').ids)
        ])

        # Check if any of the planned days have some work time set
        any_planned_time_set = any(
            not tools.float_is_zero(
                sum(
                    day.mapped('line_ids').filtered(lambda l: l.code in CODES_TO_USE).mapped('worked_time_total')
                ), precision_digits=2
            ) for day in planned_schedule_days
        )

        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        next_day_after_date_to = (date_to_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '<=', next_day_after_date_to),
            ('date', '>=', date_from)
        ]).mapped('date')

        for holiday in holidays:
            # Find intersecting dates
            date_from_intersection = max(holiday.date_from_date_format, date_from)
            date_to_intersection = min(holiday.date_to_date_format, date_to)
            if date_from_intersection > date_to_intersection:
                continue

            # Parse dates
            date_from_intersection_dt = datetime.strptime(date_from_intersection, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_intersection_dt = datetime.strptime(date_to_intersection, tools.DEFAULT_SERVER_DATE_FORMAT)

            # Find planned days for period
            planned_holiday_days = planned_schedule_days.filtered(
                lambda d: date_from_intersection <= d.date <= date_to_intersection
            )

            # Determine work norm adjustment type
            if holiday.holiday_status_id in use_planned_schedule_holiday_statuses and any_planned_time_set:
                adjustment_type = 'by_planned_schedule'
            elif holiday.holiday_status_id in use_set_hours_statuses:
                adjustment_type = 'by_set_hours'
            else:
                adjustment_type = 'by_post_and_work_norm'

            # Some types of holiday have a maximum amount of hours that can be deducted
            hour_limit = None
            if holiday.holiday_status_id == self.env.ref('hr_holidays.holiday_status_M'):
                hour_limit = 8.0

            # Find related work schedule code and determine if the holiday is by default set for the entire day
            related_work_schedule_code = related_work_schedule_codes.filtered(
                lambda code: code.tabelio_zymejimas_id == holiday.holiday_status_id.tabelio_zymejimas_id
            )
            should_be_whole_day = related_work_schedule_code and related_work_schedule_code[0].is_whole_day

            # Loop through each date
            while date_from_intersection_dt <= date_to_intersection_dt:
                date = date_from_intersection_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                date_dt = date_from_intersection_dt

                next_day = (date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                next_day_is_holiday = next_day in national_holiday_dates

                date_from_intersection_dt += relativedelta(days=1)

                # Get appointment and schedule template
                appointment = appointments.filtered(
                    lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date)
                )
                if not appointment:
                    continue
                schedule_template = appointment.schedule_template_id
                if not schedule_template:
                    continue

                # Check if the weekday is the schedule day off
                should_be_day_off = date_dt.weekday() in schedule_template.off_days()

                # Determine schedule type
                regular_schedule = schedule_template.template_type in ['fixed', 'suskaidytos']

                # Find planned day for date
                planned_day = planned_holiday_days.filtered(lambda d: d.date == date)

                regular_work_norm = super(HrEmployee, self).employee_work_norm(date, date, employee, contract,
                                                                               appointment,
                                                                               calculate_for_six_day_week,
                                                                               skip_leaves=False)

                # Determine how many hours of holiday should be calculated
                if not regular_schedule and adjustment_type == 'by_planned_schedule' and planned_day:
                    # Use planned time
                    planned_day_lines = planned_day.mapped('line_ids').filtered(lambda l: l.code in CODES_TO_USE)
                    if not planned_day_lines:
                        planned_day_lines = planned_day.mapped('line_ids').filtered(
                            lambda l: l.code == related_work_schedule_code.code
                        )
                    to_add = sum(planned_day_lines.mapped('worked_time_total'))

                    # Planned schedule is usually shortened by an hour before holidays. When the system gets the
                    # regular work norm for time during holiday days - it checks if there's any time set in ziniarastis
                    # and in holiday cases - there is not. In such cases the system assumes that the work norm for the
                    # entire day should be the work norm before shortening before the holidays. Therefore it is
                    # necessary to check such cases and adjust the planned time to add for the holiday date.
                    if next_day_is_holiday and appointment.schedule_template_id.shorter_before_holidays and \
                            appointment.schedule_template_id.template_type == 'sumine':
                        regular_hours = regular_work_norm.get('hours')
                        work_norm_difference = abs(regular_hours-to_add)
                        diff_less_than_an_hour = tools.float_compare(work_norm_difference, 1.0, precision_digits=2) <= 0
                        worked_time_less_than_norm = tools.float_compare(to_add, regular_hours, precision_digits=2) < 0
                        if diff_less_than_an_hour and worked_time_less_than_norm:
                            to_add += work_norm_difference

                    # Some holidays have hour limit
                    if hour_limit:
                        to_add = min(hour_limit, to_add)

                    # Increase leave days
                    if (not tools.float_is_zero(to_add, precision_digits=2) or should_be_whole_day) and \
                            not should_be_day_off:
                        leave_days += 1

                    leave_hours += to_add  # Increase leave hours
                elif not regular_schedule and adjustment_type == 'by_set_hours':
                    # Find ziniarastis day for date
                    ziniarastis_date_days = ziniarastis_days.filtered(lambda d: d.date == date)
                    ziniarastis_date_lines = ziniarastis_date_days.mapped('ziniarastis_day_lines')

                    # Use factually set hours to subtract the work norm.
                    related_holiday_code = holiday.holiday_status_id.tabelio_zymejimas_id.code
                    related_lines = ziniarastis_date_lines.filtered(lambda l: l.code == related_holiday_code)
                    to_add = sum(related_lines.mapped('total_worked_time_in_hours'))

                    # Some holidays have hour limit
                    if hour_limit:
                        to_add = min(hour_limit, to_add)

                    # Subtract day from work norm only if the entire day is set with the holiday code
                    subtract_days = related_lines == ziniarastis_date_lines

                    # Increase leave days
                    if (not tools.float_is_zero(to_add, precision_digits=2) and subtract_days) and \
                            not should_be_day_off:
                        leave_days += 1

                    leave_hours += to_add  # Increase leave hours
                else:
                    # Use regular work norm
                    hours = regular_work_norm.get('hours', 0.0)
                    # Some holidays have hour limit
                    if hour_limit:
                        hours = min(hour_limit, hours)
                    # Increase leave duration
                    leave_hours += hours
                    leave_days += regular_work_norm.get('days', 0.0)

        # Subtract hours from work norm
        hours = work_norm.get('hours', 0.0) - leave_hours
        days = work_norm.get('days', 0) - leave_days
        return {'hours': max(hours, 0.0), 'days': max(days, 0.0)}
