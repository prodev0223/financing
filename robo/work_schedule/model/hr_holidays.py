# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, models, tools, fields
from odoo.addons.l10n_lt_payroll.model.darbuotojai import get_vdu
from odoo.addons.l10n_lt_payroll.model.schedule_tools import merge_line_values
from odoo.addons.l10n_lt_payroll.model.darbuotojai import PROBATION_LAW_CHANGE_DATE


def str_to_dt(date_str):
    return datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)


def get_num_work_days(env, date_from, date_to, employee_id=False):
    if employee_id:
        appointments = env['hr.contract.appointment'].search([
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
            ('employee_id', '=', employee_id.id)
        ])
        template_types = appointments.mapped('schedule_template_id.template_type')
        if any(template_type in ['fixed', 'suskaidytos'] for template_type in template_types):
            planned_work_schedule = env.ref('work_schedule.planned_company_schedule')
            work_schedule_days = env['work.schedule.day'].sudo().search([
                ('date', '<=', date_to),
                ('date', '>=', date_from),
                ('employee_id', '=', employee_id.id),
                ('work_schedule_id.id', '=', planned_work_schedule.id),
                ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True)
            ])
            if work_schedule_days:
                return len(work_schedule_days.filtered(
                    lambda d: not tools.float_is_zero(
                        sum(d.mapped('line_ids.worked_time_total')),
                        precision_digits=2
                    )
                ))
    date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
    date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
    related_national_holidays = env['sistema.iseigines'].search([('date', '<=', date_from),
                                                                 ('date', '>=', date_to)]).mapped('date')
    num_days = 0
    while date_dt <= date_to_dt:
        if date_dt.weekday() not in (5, 6) and date_dt.strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT) not in related_national_holidays:
            num_days += 1
        date_dt += timedelta(days=1)
    return num_days


def check_first_two_days(date_from, date_to, employee_id=False, env=False, on_probation=False,
                         national_holiday_dates=None, week_days_off=(5, 6)):
    """
    Checks how many days should be paid for illness leave (max 2) based on work days
    Args:
        date_from (date): illness leave start
        date_to (date): illness leave end
        employee_id (hr.employee): employee to check for
        env (odoo environment): odoo environment object used for scheduled day searches
        on_probation (bool): is the employee for the leave still on probation
        national_holiday_dates (list): list of national holiday dates
        week_days_off (list): list of week days off - 0-6

    Returns: (integer) number of days that should be paid for illness leave
    """
    def _strf(date_to_convert):
        if not isinstance(date_to_convert, datetime):
            return date_to_convert
        return date_to_convert.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def is_day_off(date_to_check):
        if not isinstance(date_to_check, datetime):
            date_to_check = datetime.strptime(date_to_check, tools.DEFAULT_SERVER_DATE_FORMAT)
        return date_to_check.weekday() in week_days_off

    def is_national_holiday_date(date_to_check):
        if isinstance(date_to_check, datetime):
            date_to_check = _strf(date_to_check)
        return date_to_check in national_holiday_dates

    def is_regular_work_day(date_to_check):
        return not is_day_off(date_to_check) and not is_national_holiday_date(date_to_check)

    def is_on_probation(date_to_check):
        if isinstance(date_to_check, datetime):
            date_to_check = _strf(date_to_check)
        return on_probation and date_to_check < PROBATION_LAW_CHANGE_DATE

    def is_compensated_day(date_to_check):
        return is_regular_work_day(date_to_check) and not is_on_probation(date_to_check)

    date_to = min(date_to, (date_from + relativedelta(days=1)))
    date_to_str = _strf(date_to)
    date_from_str = _strf(date_from)

    if not national_holiday_dates:
        if not env:
            national_holiday_dates = list()
        else:
            national_holiday_dates = env['sistema.iseigines'].search([
                ('date', '<=', date_to_str),
                ('date', '>=', date_from_str)
            ]).mapped('date')

    if employee_id and env:
        work_schedule_days = env['work.schedule.day'].sudo().search([
            ('date', '<=', date_to_str),
            ('date', '>=', date_from_str),
            ('employee_id', '=', employee_id.id),
            ('work_schedule_id.id', '=', env.ref('work_schedule.planned_company_schedule').id),
            ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True)
        ])
        accumulative_work_time_appointments = env['hr.contract.appointment'].sudo().search([
            ('schedule_template_id.template_type', '=', 'sumine'),
            ('employee_id', '=', employee_id.id),
            ('date_start', '<=', date_to_str),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from_str)
        ])
        number_of_days = 0
        for work_schedule_day in work_schedule_days:
            has_planned_time_set = not tools.float_is_zero(
                sum(work_schedule_day.mapped('line_ids.worked_time_total')), precision_digits=2
            )
            date = work_schedule_day.date
            has_accumulative_accounting_app = accumulative_work_time_appointments.filtered(
                lambda a: a.date_start <= date and (not a.date_end or a.date_end >= date)
            )
            date_is_national_holiday = date in national_holiday_dates and not has_accumulative_accounting_app
            if has_planned_time_set and not is_on_probation(date) and not date_is_national_holiday:
                number_of_days += 1
        if work_schedule_days:
            return number_of_days

    delta = date_to - date_from
    if delta.days < 0:
        return 0  # Incorrect date range specified
    days_to_check = [date_from]  # Check the first day
    if delta.days > 0:
        days_to_check.append(date_from+relativedelta(days=1))  # Also check the second day
    return sum(1 if is_compensated_day(date) else 0 for date in days_to_check)


class HrHolidays(models.Model):
    _inherit = 'hr.holidays'

    holiday_is_for_the_entire_day = fields.Boolean(compute='_compute_holiday_is_for_the_entire_day')

    @api.multi
    @api.depends('holiday_status_id', 'date_from', 'date_to')
    def _compute_holiday_is_for_the_entire_day(self):
        related_schedule_holiday_codes = self.env['work.schedule.codes'].search([
            ('tabelio_zymejimas_id', 'in', self.mapped('holiday_status_id.tabelio_zymejimas_id').ids)
        ])
        for rec in self:
            record_work_schedule_code = related_schedule_holiday_codes.filtered(
                lambda rshc: rshc.tabelio_zymejimas_id == rec.holiday_status_id.tabelio_zymejimas_id
            )
            # Treat as whole day if for some reason work schedule code is not found
            is_whole_day = not record_work_schedule_code or record_work_schedule_code.is_whole_day
            if not is_whole_day:
                # Even if the schedule code says that the marking is not for the whole day, ensure that the holiday is
                # for a single day
                is_whole_day = rec.date_from_date_format != rec.date_to_date_format
            rec.holiday_is_for_the_entire_day = is_whole_day

    @api.multi
    @api.depends('holiday_status_id', 'employee_id', 'vdu', 'date_from', 'date_to', 'sick_leave_continue')
    def _compute_npsd(self):
        for rec in self:
            npsd = 0.0
            is_liga = rec.holiday_status_id.kodas == 'L'
            continuation = rec.sick_leave_continue
            fields_are_set = rec.employee_id and rec.vdu and rec.date_from and rec.date_to

            # These new calculations based on planned time (in hours) take affect from December 1st. 2021
            use_planned_hours_start_date = '2021-12-01'

            if is_liga and not continuation and fields_are_set and \
                    (not rec.on_probation or rec.date_to_date_format >= PROBATION_LAW_CHANGE_DATE):
                koeficientas = rec.company_id.with_context(date=rec.date_from[:10]).ligos_koeficientas

                date_from_str = rec.date_from[:10]

                date_from_dt = datetime.strptime(date_from_str, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(rec.date_to[:10], tools.DEFAULT_SERVER_DATE_FORMAT)

                payslip_start = date_from_dt + relativedelta(day=1)
                payslip_end = date_to_dt + relativedelta(day=31)

                contract = rec.employee_id.contract_id.with_context(date=payslip_start)
                schedule_template = rec.appointment_id.schedule_template_id

                npsd = 0.0
                vdu = 0.0
                planned_schedule_days = None
                if schedule_template.template_type == 'sumine':
                    vdu = get_vdu(self.env, rec.date_from_date_format, rec.employee_id,
                                  contract_id=rec.contract_id.id, vdu_type='h').get('vdu', 0.0)
                    max_date_to = (date_from_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    max_date_to = min(max_date_to, rec.date_to_date_format)
                    worked_time_codes = self.env['hr.payslip'].get_salary_work_time_codes().get('normal', list())
                    planned_schedule_days = self.env['work.schedule.day'].sudo().search([
                        ('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
                        ('employee_id', '=', rec.employee_id.id),
                        ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True),
                        ('date', '<=', max_date_to),
                        ('date', '>=', rec.date_from_date_format),
                        ('line_ids', '!=', False),
                        ('line_ids.code', 'in', list(worked_time_codes)),
                        ('date', '>=', use_planned_hours_start_date)
                    ])
                if planned_schedule_days:
                    planned_lines = planned_schedule_days.mapped('line_ids').filtered(
                        lambda l: str(l.code) in worked_time_codes
                    )
                    total_planned_time = sum(planned_lines.mapped('worked_time_total'))
                    npsd = total_planned_time * vdu * koeficientas
                starts_before_the_hourly_calculations = rec.date_from_date_format < use_planned_hours_start_date
                ends_after_the_hourly_calculations = rec.date_to_date_format >= use_planned_hours_start_date
                if not planned_schedule_days or starts_before_the_hourly_calculations:
                    if contract.struct_id.code == 'MEN':
                        mma = contract.get_payroll_tax_rates(['mma'])['mma']
                        number_work_days = get_num_work_days(
                            self.env,
                            str(payslip_start.date()),
                            str(payslip_end.date())
                        )
                        min_day_pay = mma / float(number_work_days) if number_work_days > 0 else 0.0  # P3:DivOK
                        min_day_pay *= schedule_template.etatas or 1.0
                    elif contract.struct_id.code == 'VAL':
                        min_day_pay = contract.employee_id.get_minimum_wage_for_date(rec.date_to_date_format)['day']
                    else:
                        min_day_pay = 0.0
                    amount_to_use = max(rec.vdu, min_day_pay)
                    pay_per_day = koeficientas * amount_to_use
                    date_to_max = date_to_dt
                    if starts_before_the_hourly_calculations and ends_after_the_hourly_calculations:
                        # Partial NPSD (after date) has already been computed by planned time hours so compute up to
                        # the change date
                        use_planned_hours_start_date_dt = datetime.strptime(use_planned_hours_start_date,
                                                                            tools.DEFAULT_SERVER_DATE_FORMAT)
                        date_to_max += relativedelta(
                            month=use_planned_hours_start_date_dt.month,
                            year=use_planned_hours_start_date_dt.year,
                            day=use_planned_hours_start_date_dt.day
                        )
                        date_to_max -= relativedelta(days=1)  # Day before

                    date_to_max_str = date_to_max.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                    national_holiday_dates = self.env['sistema.iseigines'].search([
                        ('date', '>=', date_from_str),
                        ('date', '<=', date_to_max_str)
                    ]).mapped('date')

                    week_days_off = schedule_template.off_days() if schedule_template else [5, 6]

                    number_absence_days = check_first_two_days(date_from_dt, date_to_max, employee_id=rec.employee_id,
                                                               env=self.env, on_probation=rec.on_probation,
                                                               national_holiday_dates=national_holiday_dates,
                                                               week_days_off=week_days_off)
                    npsd += round(pay_per_day * number_absence_days, 2)
            rec.npsd = npsd

    @api.multi
    def stop_in_the_middle(self, date):
        """
        Shorten an existing confirmed leave record
        :param date: last holiday day, type: str, format DEFAULT_SERVER_DATE_FORMAT
        :return: None
        """

        factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        backup_schedule = self.env.ref('work_schedule.holiday_backup_schedule')

        for rec in self:
            date_from = rec.date_from_date_format
            date_to = rec.date_to_date_format
            employee = rec.employee_id
            work_schedule_holiday = self.env['work.schedule.holidays'].sudo().search([
                ('date_from', '=', date_from),
                ('date_to', '=', date_to),
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', rec.holiday_status_id.id)
            ])

            days = self.env['work.schedule.day'].sudo().search([
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('employee_id', '=', employee.id)
            ])

            super(HrHolidays, rec).stop_in_the_middle(date)

            work_schedule_holiday.write({'date_to': date})

            days_to_update = days.filtered(lambda d: d.state == 'draft' and d.date > date)
            factual_days = days_to_update.filtered(lambda d: d.work_schedule_id.id == factual_schedule.id)
            planned_days = days_to_update.filtered(lambda d: d.work_schedule_id.id == planned_schedule.id)
            backup_days = days_to_update.filtered(lambda d: d.work_schedule_id.id == backup_schedule.id)
            set_default_value_days = self.env['work.schedule.day']
            for factual_day in factual_days:
                factual_day.line_ids.unlink()
                backup_day = backup_days.filtered(
                    lambda d: d.date == factual_day.date and d.department_id == factual_day.department_id)
                planned_day = planned_days.filtered(
                    lambda d: d.date == factual_day.date and d.department_id == factual_day.department_id)
                if backup_day.line_ids:
                    for line in backup_day.line_ids:
                        line.copy({'day_id': factual_day.id})
                elif planned_day.line_ids:
                    for line in planned_day.line_ids:
                        line.copy({'day_id': factual_day.id})
                else:
                    set_default_value_days |= factual_day
            set_default_value_days.set_default_schedule_day_values()

    @api.multi
    def action_approve(self):
        res = super(HrHolidays, self).action_approve()
        planned_company_schedule = self.env.ref('work_schedule.planned_company_schedule')
        school_year_start_half_day_leave_hol_status_id = self.env.ref('hr_holidays.holiday_status_MP').id
        school_year_start_schedule_code = self.env['work.schedule.codes'].search(
            [('tabelio_zymejimas_id', '=', self.env.ref('l10n_lt_payroll.tabelio_zymejimas_MP').id)])

        downtime_holiday_status_id = self.env.ref('hr_holidays.holiday_status_PN').id

        skip_holiday_creation_holiday_status_ids = (
            downtime_holiday_status_id,
        )
        for rec in self.filtered(lambda h: h.holiday_status_id.id not in skip_holiday_creation_holiday_status_ids):
            try:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
            is_komandiruote = rec.holiday_status_id.kodas == 'K'

            days = self.env['work.schedule.day'].search([
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('employee_id', '=', rec.employee_id.id),
                ('work_schedule_id.schedule_type', '=', 'factual')
            ])
            day_holidays = days.mapped('schedule_holiday_id')

            if is_komandiruote:
                days.write({'business_trip': True})
                continue

            day_holidays |= self.env['work.schedule.holidays'].search([
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from),
                ('employee_id', '=', rec.employee_id.id)
            ])
            day_holidays.unlink(bypass_confirmed=True, holiday_id_being_created=rec.id)

            if days and self.sudo().env.user.company_id.update_planned_schedule_on_holiday_set == 'update':
                schedule_lines = days.mapped('work_schedule_line_id')
                for line in schedule_lines:
                    planned_schedule_line = self.env['work.schedule.line'].search([
                        ('employee_id', '=', line.employee_id.id),
                        ('department_id', '=', line.department_id.id),
                        ('year', '=', line.year),
                        ('month', '=', line.month),
                        ('work_schedule_id.schedule_type', '=', 'planned')
                    ])
                    if not planned_schedule_line:
                        planned_company_schedule.with_context(do_not_fill_schedule=True).create_empty_schedule(line.year,
                                                                                                       line.month,
                                                                                                       [
                                                                                                           line.employee_id.id],
                                                                                                       [
                                                                                                           line.department_id.id],
                                                                                                       True)
                planned_schedule_days = self.env['work.schedule.day'].search([
                    ('date', 'in', days.mapped('date')),
                    ('employee_id', '=', rec.employee_id.id),
                    ('work_schedule_id.schedule_type', '=', 'planned')
                ])
                for day in days:
                    planned_day = planned_schedule_days.filtered(lambda d: d.date == day.date and
                                                                           d.department_id == day.department_id)
                    if planned_day:
                        planned_day_lines = planned_day.mapped('line_ids')
                        planned_day_factual_lines = planned_day_lines.filtered(
                            lambda l: not l.work_schedule_code_id.is_holiday and
                                      not l.work_schedule_code_id.is_absence
                        )
                        planned_factual_work_time = sum(planned_day_factual_lines.mapped('worked_time_total'))
                        if tools.float_is_zero(planned_factual_work_time, precision_digits=2):
                            factual_day_work_lines = day.mapped('line_ids').filtered(
                                lambda l: not l.work_schedule_code_id.is_holiday and
                                          not l.work_schedule_code_id.is_absence
                            )
                            for factual_day_line in factual_day_work_lines:
                                factual_day_line.copy({'day_id': planned_day.id})

            school_year_start_case = rec.holiday_status_id.id == school_year_start_half_day_leave_hol_status_id
            LineObj = self.env['work.schedule.day.line']
            if school_year_start_case:
                dt_from = str_to_dt(rec.date_from)
                dt_to = str_to_dt(rec.date_to)
                lines_in_range = days.mapped('line_ids').filtered(
                    lambda l: str_to_dt(l.datetime_from) <= dt_to and str_to_dt(l.datetime_to) >= dt_from)
                for line in lines_in_range:
                    if str_to_dt(line.datetime_to) > dt_to > str_to_dt(line.datetime_from):
                        time_start = round((dt_to.hour + dt_to.minute / 60.0), 2)  # P3:DivOK

                        LineObj.create({
                            'day_id': line.day_id.id,
                            'work_schedule_code_id': school_year_start_schedule_code.id,
                            'time_from': line.time_from,
                            'prevent_deletion': True,
                            'time_to': time_start
                        })

                        line.write({'time_from': time_start})
                    else:
                        line.write({
                            'work_schedule_code_id': school_year_start_schedule_code.id,
                            'prevent_deletion': True,
                        })
            else:
                if rec.holiday_is_for_the_entire_day:
                    # Unlink days that don't have related holidays set
                    days.mapped('line_ids').filtered(lambda l: not l.matched_holiday_id or l.holiday_id == rec).unlink()
                    self.env['work.schedule.holidays'].create({
                        'employee_id': rec.employee_id.id,
                        'date_from': date_from,
                        'date_to': date_to,
                        'holiday_status_id': rec.holiday_status_id.id})
                elif days:
                    dates = list(set(days.mapped('date')))  # Map days

                    # Parse holiday times (even though the holiday might span multiple days)
                    holiday_time_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    holiday_time_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    holiday_time_from = holiday_time_from.hour + holiday_time_from.minute / 60.0  # P3:DivOK
                    holiday_time_to = holiday_time_to.hour + holiday_time_to.minute / 60.0  # P3:DivOK

                    # Find planned lines
                    planned_lines = self.env['work.schedule.day.line'].search([
                        ('employee_id', '=', rec.employee_id.id),
                        ('date', 'in', dates),
                        ('day_id.work_schedule_id.schedule_type', '=', 'planned'),
                        ('day_id.work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True)
                    ])
                    # Loop through dates
                    for date in dates:
                        # Find date days (multiple days due to multiple departments)
                        date_days = days.filtered(lambda d: d.date == date)

                        # Find overlapping lines
                        lines = date_days.mapped('line_ids')
                        overlapping_lines = lines.filtered(lambda l: l.time_from <= holiday_time_to and
                                                                     l.time_to >= holiday_time_from)

                        # Unlink lines that don't have a related holiday
                        overlapping_lines.filtered(lambda l: not l.holiday_id and not l.matched_holiday_id).unlink()
                        lines = lines.exists()

                        existing_line_times = [(l.time_from, l.time_to) for l in lines]
                        date_planned_lines = planned_lines.filtered(lambda l: l.date == date)

                        if date_planned_lines:
                            # Keep data from planned schedule and merge the times around existing lines
                            planned_times = [(l.time_from, l.time_to) for l in date_planned_lines]
                            merged_times = merge_line_values(planned_times, existing_line_times)
                        else:
                            # Find regular hours for date and merge around existing times
                            appointment = rec.employee_id.with_context(date=date).appointment_id
                            schedule_template = appointment and appointment.schedule_template_id
                            if not schedule_template:
                                continue
                            regular_hours = schedule_template.get_regular_hours(date)
                            if not regular_hours or tools.float_is_zero(regular_hours, precision_digits=2):
                                regular_hours = schedule_template.avg_hours_per_day
                            time_from, time_to = 8.0, 8.0 + regular_hours
                            merged_times = merge_line_values([(time_from, time_to)], existing_line_times)

                        # Times to set are the merged times that didn't exist before
                        # (x for x in merged times if x not in existing_line_times)
                        times_to_set = [mt for mt in merged_times if not any(
                            tools.float_compare(et[0], mt[0], precision_digits=2) == 0 and
                            tools.float_compare(et[0], mt[0], precision_digits=2) == 0 for et in existing_line_times
                        )]

                        if not times_to_set:
                            continue

                        # Pick one of the department days to set time for
                        day_to_fill = None
                        employee_main_department = rec.employee_id.department_id
                        if employee_main_department:
                            # Try to add the line to the main department of the employee
                            day_to_fill = date_days.filtered(
                                lambda day: day.department_id == employee_main_department)
                        if not day_to_fill:
                            day_to_fill = date_days[0]

                        # Get work schedule code
                        work_schedule_code = self.env['work.schedule.codes'].search([
                            ('tabelio_zymejimas_id', '=', rec.holiday_status_id.tabelio_zymejimas_id.id)
                        ], limit=1)

                        # Create work schedule day lines
                        for time_to_set in times_to_set:
                            self.env['work.schedule.day.line'].create({
                                'work_schedule_code_id': work_schedule_code.id,
                                'time_from': time_to_set[0],
                                'time_to': time_to_set[1],
                                'day_id': day_to_fill.id,
                                'prevent_deletion': True,
                                'holiday_id': rec.id
                            })

        for rec in self.filtered(lambda h: h.holiday_status_id.id == downtime_holiday_status_id):
            downtime_record = self.env['hr.employee.downtime'].sudo().search([
                ('holiday_id', '=', rec.id)
            ])
            if not downtime_record:
                continue

            factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
            planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
            backup_schedule = self.env.ref('work_schedule.holiday_backup_schedule')

            date_from = rec.date_from_date_format
            date_to = rec.date_to_date_format

            national_holidays = self.env['sistema.iseigines'].search([
                ('date', '<=', date_to),
                ('date', '>=', date_from)
            ]).mapped('date')

            downtime_schedule_days = self.env['work.schedule.day'].search([
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('employee_id', '=', rec.employee_id.id),
                ('work_schedule_id', 'in', [backup_schedule.id, factual_schedule.id, planned_schedule.id]),
                ('state', 'in', ['draft'])
            ])

            factual_days = downtime_schedule_days.filtered(lambda d: d.work_schedule_id.id == factual_schedule.id)
            backup_days = downtime_schedule_days.filtered(lambda d: d.work_schedule_id.id == backup_schedule.id)
            planned_days = downtime_schedule_days.filtered(lambda d: d.work_schedule_id.id == planned_schedule.id)

            periods = set((day.work_schedule_line_id.year, day.work_schedule_line_id.month,
                           day.work_schedule_line_id.department_id.id) for day in factual_days)
            for (year, month, department_id) in periods:
                period_backup_days = backup_days.filtered(lambda d: d.work_schedule_line_id.year == year and
                                                                    d.work_schedule_line_id.month == month and
                                                                    d.work_schedule_line_id.department_id.id == department_id)
                if not period_backup_days:
                    backup_schedule.create_empty_schedule(
                        year,
                        month,
                        employee_ids=rec.employee_id.ids,
                        department_ids=[department_id]
                    )

            backup_days = self.env['work.schedule.day'].search([
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('employee_id', '=', rec.employee_id.id),
                ('work_schedule_id.id', '=', backup_schedule.id),
                ('state', '=', 'draft')
            ])

            fd_zymejimas = self.env.ref('work_schedule.work_schedule_code_FD')
            pn_zymejimas = self.env.ref('work_schedule.work_schedule_code_PN')

            now = datetime.utcnow()
            first_of_this_month = now + relativedelta(day=1)

            if downtime_record.downtime_type == 'full':
                days_to_regular_fill = self.env['work.schedule.day']
                # Sort days by employee department
                factual_days = factual_days.sorted(key=lambda d: d.department_id.id != d.employee_id.department_id.id)
                for day in factual_days:
                    if day.date in days_to_regular_fill.mapped('date'):
                        # Don't change the days of other departments if regular time will already be set for one of the
                        # departments
                        continue
                    day_date_dt = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    first_of_month_for_day_date = day_date_dt + relativedelta(day=1)
                    # We're setting downtime for the future and copying planned schedule to factual will override
                    # factual therefore we should be editing the planned day rather than the factual day.
                    if first_of_month_for_day_date > first_of_this_month:
                        planned_day = planned_days.filtered(lambda d: d.date == day.date and
                                                                      d.department_id == day.department_id and
                                                                      d.employee_id == day.employee_id)
                        if planned_day:
                            day = planned_day[0]

                    backup_day = backup_days.filtered(
                        lambda d: d.date == day.date and d.department_id == day.department_id)
                    if not backup_day:
                        continue  # Safety net not to loose data
                    backup_day.line_ids.unlink()
                    for day_line in day.line_ids:
                        day_line.copy({'day_id': backup_day.id})
                    day.line_ids.unlink()

                    dont_fill_weekdays = [5, 6]
                    day_appointment = day.appointment_id
                    if day_appointment and \
                            day_appointment.schedule_template_id.template_type in ['fixed', 'suskaidytos'] and \
                            day_appointment.schedule_template_id.work_week_type == 'six_day':
                        dont_fill_weekdays = [5]

                    day_date_dt = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if day_date_dt.weekday() not in dont_fill_weekdays and day.date not in national_holidays:
                        days_to_regular_fill |= day

                days_to_regular_fill.with_context(force_do_not_use_planned=True).set_default_schedule_day_values()
                days_to_regular_fill.mapped('line_ids').write({
                    'work_schedule_code_id': pn_zymejimas.id
                })
            else:
                if downtime_record.employee_schedule_is_regular:
                    downtime_schedule = downtime_record.downtime_schedule_line_ids
                    for downtime_schedule_day in factual_days:
                        day_date_dt = datetime.strptime(downtime_schedule_day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                        first_of_month_for_day_date = day_date_dt + relativedelta(day=1)
                        # We're setting downtime for the future and copying planned schedule to factual will override
                        # factual therefore we should be editing the planned day rather than the factual day.
                        if first_of_month_for_day_date > first_of_this_month:
                            planned_day = planned_days.filtered(lambda d: d.date == downtime_schedule_day.date and
                                                                          d.department_id == downtime_schedule_day.department_id and
                                                                          d.employee_id == downtime_schedule_day.employee_id)
                            if planned_day:
                                downtime_schedule_day = planned_day[0]

                        backup_day = backup_days.filtered(
                            lambda
                                d: d.date == downtime_schedule_day.date and d.department_id == downtime_schedule_day.department_id)
                        if not backup_day:
                            continue  # Safety net not to loose data
                        backup_day.line_ids.unlink()
                        for day_line in downtime_schedule_day.line_ids:
                            day_line.copy({'day_id': backup_day.id})
                        day_date_dt = datetime.strptime(downtime_schedule_day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                        day_downtime_schedule = downtime_schedule.filtered(
                            lambda l: l.weekday == str(day_date_dt.weekday()))
                        work_times = [(l.time_from, l.time_to) for l in day_downtime_schedule]

                        if downtime_schedule_day.date not in national_holidays or downtime_schedule_day.line_ids:
                            schedule = work_times
                            downtime_times = [(l.time_from, l.time_to, pn_zymejimas.id) for l in
                                              downtime_schedule_day.line_ids]
                            downtime_schedule_day.line_ids.unlink()
                            schedule_lines = merge_line_values(schedule, downtime_times)

                            for schedule_line in schedule_lines:
                                try:
                                    marking = schedule_line[2]
                                    if not marking:
                                        marking = fd_zymejimas.id
                                except IndexError:
                                    marking = fd_zymejimas.id
                                self.env['work.schedule.day.line'].create({
                                    'date': downtime_schedule_day.date,
                                    'day_id': downtime_schedule_day.id,
                                    'time_from': schedule_line[0],
                                    'time_to': schedule_line[1],
                                    'work_schedule_code_id': marking,
                                })
                            downtime_schedule_day.write({'free_day': False})
                else:
                    # Clients should fill the schedule, or we should discuss how to properly do it
                    pass

        return res

    @api.multi
    def action_refuse(self):
        days_to_update = list()

        downtime_holiday_status_id = self.env.ref('hr_holidays.holiday_status_PN')

        factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        backup_schedule = self.env.ref('work_schedule.holiday_backup_schedule')

        set_default_value_days = self.env['work.schedule.day']

        lines_to_unlink = self.env['work.schedule.day.line']

        for rec in self:
            try:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_id = rec.employee_id.id
            days = self.env['work.schedule.day'].search([
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('employee_id', '=', employee_id)
            ])
            self.env['work.schedule.holidays'].search([
                ('date_from', '=', rec.date_from_date_format),
                ('date_to', '=', rec.date_to_date_format),
                ('employee_id', '=', employee_id),
                ('holiday_status_id', '=', rec.holiday_status_id.id)
            ]).unlink(bypass_confirmed=True, remove_confirmed=True)

            is_komandiruote = rec.holiday_status_id.tabelio_zymejimas_id.code == 'K'

            if is_komandiruote:
                days.with_context(no_raise=True, no_business_trip_reset=True).write({'business_trip': False})
                continue

            # Work schedule day lines should be recreated if a holiday is canceled
            # for an employee with a particular schedule type ('fixed' or 'suskaidytos')
            employee_appointments_during_leaves = rec.employee_id.appointment_ids.filtered(
                lambda app: app.date_start <= rec.date_to_date_format and
                            (not app.date_end or app.date_end >= rec.date_from_date_format)
            )
            unique_schedule_template_types_during_period = list(set(
                employee_appointments_during_leaves.mapped('schedule_template_id.template_type')
            ))
            restore_schedule = all(i in ['fixed', 'suskaidytos'] for i in unique_schedule_template_types_during_period)

            if rec.holiday_status_id.id == downtime_holiday_status_id.id or restore_schedule:
                days = days.filtered(lambda d: d.state in ['draft'])
                factual_days = days.filtered(lambda d: d.work_schedule_id.id == factual_schedule.id)
                planned_days = days.filtered(lambda d: d.work_schedule_id.id == planned_schedule.id)
                backup_days = days.filtered(lambda d: d.work_schedule_id.id == backup_schedule.id)
                for factual_day in factual_days:
                    factual_day.line_ids.unlink()
                    backup_day = backup_days.filtered(
                        lambda d: d.date == factual_day.date and d.department_id == factual_day.department_id)
                    planned_day = planned_days.filtered(
                        lambda d: d.date == factual_day.date and d.department_id == factual_day.department_id)
                    if backup_day.line_ids:
                        for line in backup_day.line_ids:
                            line.copy({'day_id': factual_day.id})
                    elif planned_day.line_ids:
                        for line in planned_day.line_ids:
                            line.copy({'day_id': factual_day.id})
                    else:
                        set_default_value_days |= factual_day

            lines_to_unlink |= days.mapped('line_ids').filtered(lambda l: l.matched_holiday_id == rec or
                                                                          l.holiday_id == rec)

            # Not all lines might be linked to holiday so if the holiday is for the entire day - find lines with same
            # code and unlink
            lines_to_unlink |= days.mapped('line_ids').filtered(
                lambda l: l.code == rec.holiday_status_code and l.work_schedule_code_id.is_whole_day
            )

            days_to_update += days.mapped('id')

        lines_to_unlink.exists().with_context(allow_delete_special=True).unlink()
        res = super(HrHolidays, self).action_refuse()
        set_default_value_days.set_default_schedule_day_values()
        self.env['work.schedule.day'].browse(days_to_update).mapped('schedule_holiday_id').unlink(bypass_confirmed=True)
        return res

    @api.multi
    def unlink_manual_holiday_related_records(self):
        """
        Unlink manually created work.schedule.day.line records
        :return: None
        """
        self.ensure_one()
        if not self.env.user.is_schedule_super():
            return
        days = self.env['work.schedule.day'].search([
            ('date', '>=', self.date_from_date_format),
            ('date', '<=', self.date_to_date_format),
            ('employee_id', '=', self.employee_id.id)
        ])

        related_lines = days.mapped('line_ids').filtered(
            lambda x: x.tabelio_zymejimas_id.id == self.holiday_status_id.tabelio_zymejimas_id.id)
        # Deletion prevention of automatically created lines (related to hr.holidays) is handled in unlink() method
        related_lines.unlink()
