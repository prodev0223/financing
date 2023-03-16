# -*- encoding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, _, exceptions, tools

CODES_HOLIDAYS = ['A', 'G', 'KA', 'KR', 'M', 'MA', 'N', 'NA', 'ND', 'P', 'PV', 'TA']
CODES_ABSENCE = ['D', 'KM', 'KT', 'L', 'NN', 'NP', 'NS', 'PK', 'ST', 'VV']
SPECIAL_SKIP_ONLY_HOURS = ['MP', 'V', 'PN', 'PB', 'NLL']
SPECIAL_SKIP_ONLY_IF_HOURS_ARE_SET = []  # Skip days with these codes only if some time for those codes are set

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def employee_work_norm(self, calc_date_from=False, calc_date_to=False, employee=False, contract=False, appointment=False, calculate_for_six_day_week=False, skip_leaves=False):
        if not (employee or contract or appointment):
            skip_leaves = False

        date_from = calc_date_from
        date_to = calc_date_to

        shorten_before_holidays = not self._context.get('dont_shorten_before_holidays')

        if appointment:
            date_from = appointment.date_start if appointment.date_start > date_from else date_from
            date_to = appointment.date_end if appointment.date_end and (not date_to or date_to > appointment.date_end) else date_to
            contract = appointment.contract_id
        elif contract:
            date_from = contract.date_start if contract.date_start > date_from else date_from
            date_to = contract.date_end if contract.date_end and (not date_to or date_to > contract.date_end) else date_to

        if self._context.get('maximum'):
            date_from = calc_date_from
            date_to = calc_date_to
            if not appointment:
                raise exceptions.UserError(_('Negalima nustatyti maksimalaus darbo laiko.'))

        if not date_from:
            raise exceptions.UserError(_('Negalima nustatyti datos, nuo kurios skaičiuoti darbo normą'))
        if not date_to:
            raise exceptions.UserError(_('Negalima nustatyti datos, iki kurios skaičiuoti darbo normą'))

        ziniarastis_period_lines = self.env['ziniarastis.period.line']
        if employee and not contract:
            contracts = self.env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '>=', date_from),
                ('date_end', '=', False)
            ])
            if skip_leaves:
                ziniarastis_period_lines = self.env['ziniarastis.period.line'].search([
                    ('contract_id', 'in', contracts.mapped('id')),
                    ('date_from', '<=', date_to),
                    ('date_to', '>=', date_from)
                ])
        elif contract:
            ziniarastis_period_lines = self.env['ziniarastis.period.line'].search([
                ('contract_id', '=', contract.id),
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from)
            ])

        appointments = False
        if appointment:
            appointments = appointment
        elif contract:
            appointments = contract.appointment_ids.filtered(lambda app: app.date_start <= date_to and (not app.date_end or app.date_end >= date_from))
        elif employee:
            appointments = contracts.mapped('appointment_ids').filtered(lambda app: app.date_start <= date_to and (not app.date_end or app.date_end >= date_from))

        national_holidays = self.env['sistema.iseigines'].search([('date', '>=', date_from), ('date', '<=', date_to)])
        skip_codes = CODES_HOLIDAYS + CODES_ABSENCE
        hr_holidays = self.env['hr.holidays']
        if self._context.get('use_holiday_records') and appointments:
            hr_holidays = hr_holidays.sudo().search([
                ('date_to_date_format', '>=', date_from),
                ('date_from_date_format', '<=', date_to),
                ('contract_id', 'in', appointments.mapped('contract_id').ids),
                ('state', '=', 'validate')
            ])
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        hours = 0.0
        days = 0
        while date_from_dt <= date_to_dt:
            date = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            is_national_holiday = bool(national_holidays.filtered(lambda h: h.date == date))
            six_day_week = calculate_for_six_day_week
            off_days = [5, 6]
            shorter_before_holidays = True
            etatas = work_norm = 1.0
            hours_to_subtract_extra = worked_time_for_day = 0.0
            accumulative_work_time_accounting = schedule_template = based_on_work_days = \
                some_time_for_period_line_is_set = leave_is_set_in_planned_schedule = False
            is_shorter_day = not is_national_holiday and \
                             bool(self.env['sistema.iseigines'].get_dates_with_shorter_work_date(date, date))
            if appointments:
                if not self._context.get('maximum'):
                    appointment = appointments.filtered(lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date))
                if not appointment:
                    date_from_dt += relativedelta(days=1)
                    continue
                else:
                    shorter_before_holidays = shorten_before_holidays and \
                                              appointment.schedule_template_id.shorter_before_holidays
                    schedule_template = appointment.schedule_template_id
                    accumulative_work_time_accounting = schedule_template.template_type == 'sumine'
                    if is_shorter_day and shorter_before_holidays and accumulative_work_time_accounting:
                        # Get data for shorter before holidays
                        before_holidays_data = appointment.get_shorter_before_holidays_worked_time_data(date)
                        some_time_for_period_line_is_set = before_holidays_data.get('some_time_for_period_line_is_set')
                        leave_is_set_in_planned_schedule = before_holidays_data.get('leave_is_set_in_planned_schedule')
                        worked_time_for_day = before_holidays_data.get('worked_time_for_day', 0.0)
                    period_line = ziniarastis_period_lines.filtered(lambda l: l.contract_id.id == contract.id and
                                                                              l.date_from <= date <= l.date_to)
                    period_day = period_line.mapped('ziniarastis_day_ids').filtered(lambda d: d.date == date)
                    day_lines = period_day.mapped('ziniarastis_day_lines')
                    if skip_leaves:
                        contract = appointment.contract_id
                        all_period_line_day_lines = period_line.mapped('ziniarastis_day_ids.ziniarastis_day_lines')
                        period_line_worked_time_total = sum(all_period_line_day_lines.mapped('total_worked_time_in_hours'))
                        no_ziniarastis_data = tools.float_is_zero(period_line_worked_time_total, precision_digits=2)
                        if no_ziniarastis_data and self._context.get('use_holiday_records'):
                            day_holidays = hr_holidays.filtered(
                                lambda h: h.date_from_date_format <= date <= h.date_to_date_format and
                                          h.holiday_status_id.tabelio_zymejimas_id.code in skip_codes
                            )
                            if day_holidays:
                                date_from_dt += relativedelta(days=1)
                                continue
                        # Determine if line has holiday codes and if we should skip them
                        codes_in_skip_list = []
                        for day_line in day_lines:
                            code = day_line.code
                            if code in skip_codes:
                                # Extra case - we only want to skip these specific lines if there's some time set.
                                # Maybe we should do this for all codes that should be skipped...
                                if code in SPECIAL_SKIP_ONLY_IF_HOURS_ARE_SET:
                                    line_time = day_line.total_worked_time_in_hours
                                    if tools.float_is_zero(line_time, precision_digits=2):
                                        continue
                                codes_in_skip_list.append(code)
                        if codes_in_skip_list:
                            date_from_dt += relativedelta(days=1)
                            continue
                        special_cases = [line for line in day_lines if line.code in SPECIAL_SKIP_ONLY_HOURS]
                        for case in special_cases:
                            # P3:DivOK
                            hours_to_subtract_extra += case.worked_time_hours + case.worked_time_minutes / 60.0

                    work_norm = appointment.schedule_template_id.work_norm or 1.0
                    six_day_week = schedule_template.six_day_work_week
                    off_days = schedule_template.off_days()
                    salary_structure_is_monthly = appointment.sudo().struct_id.code == 'MEN'
                    attendance_lines_exist = len(schedule_template.mapped('fixed_attendance_ids.id')) > 0
                    based_on_work_days = schedule_template.work_week_type == 'based_on_template' and attendance_lines_exist
                    if salary_structure_is_monthly and appointment.schedule_template_id.men_constraint == 'val_per_men':
                        days_in_month = (date_from_dt + relativedelta(day=31)).day
                        # P3:DivOK
                        hours += appointment.schedule_template_id.max_monthly_hours / days_in_month
                        date_from_dt += relativedelta(days=1)
                        continue
                    elif appointment.schedule_template_id.men_constraint != 'val_per_men':
                        etatas = appointment.sudo().schedule_template_id.etatas

            if not is_national_holiday:
                is_work_day = False
                to_add = 0.0
                if based_on_work_days:
                    if not accumulative_work_time_accounting:
                        to_add = appointment.schedule_template_id.with_context(
                            calculating_work_norm=True,
                            force_get_regular_hours=is_shorter_day
                        ).get_regular_hours(date)
                        days += 1.0 if tools.float_compare(to_add, 0.0, precision_digits=2) > 0 else 0.0
                        is_work_day = True if tools.float_compare(to_add, 0.0, precision_digits=2) > 0 else False
                    else:
                        is_work_day = date_from_dt.weekday() not in off_days
                        if is_work_day:
                            to_add = schedule_template.avg_hours_per_day if schedule_template else 8.0 * etatas * work_norm
                elif six_day_week:
                    if date_from_dt.weekday() not in [5, 6]:
                        to_add = 7.0 * etatas * work_norm
                        days += 1.0
                        is_work_day = True
                    elif date_from_dt.weekday() == 5:
                        to_add = 5.0 * etatas * work_norm
                        days += 1.0
                        is_work_day = True
                else:
                    if date_from_dt.weekday() not in off_days:
                        to_add = 8.0 * etatas * work_norm
                        days += 1.0
                        is_work_day = True
                hours += to_add
                if is_shorter_day and shorter_before_holidays:
                    time_to_subtract = 0.0
                    if (some_time_for_period_line_is_set or leave_is_set_in_planned_schedule) and \
                            accumulative_work_time_accounting:
                        time_to_subtract = min(1.0, worked_time_for_day)
                        if not tools.float_is_zero(to_add, precision_digits=2):
                            time_to_subtract = min(time_to_subtract, to_add)
                    elif not accumulative_work_time_accounting:
                        time_to_subtract = min(1.0, to_add)
                    hours -= time_to_subtract
                    # Subtract a day if time added is the time subtracted
                    if is_work_day and not tools.float_is_zero(time_to_subtract, precision_digits=2) and \
                            tools.float_compare(to_add, time_to_subtract, precision_digits=2) <= 0:
                        days -= 1
            hours -= hours_to_subtract_extra
            date_from_dt += relativedelta(days=1)
        hours = round(hours, 2)
        return {'hours': hours, 'days': max(days, 0)}