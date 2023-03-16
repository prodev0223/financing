# -*- coding: utf-8 -*-
from __future__ import division
from collections import defaultdict

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _, exceptions, tools

from schedule_tools import merge_line_values

NIGHT_SHIFT_START = 22.0
NIGHT_SHIFT_END = 6.0
FULL_ETATAS_WEEKLY_HOURS = 40.0
DEFAULT_SCHEDULE_START = 8.0  # What time does schedule start if no schedule is defined
# P3:DivOK
ETATAS_HALF_STEP = 1.0 / 60.0 / FULL_ETATAS_WEEKLY_HOURS / 2.0  # Schedule template minimum step is one minute
ETATAS_CHECK_PRECISION_DIGITS = 4

SCHEDULE_TEMPLATE_TYPES = [
    ('fixed', 'Nekintančio darbo laiko režimas'),
    ('sumine', 'Suminės darbo laiko apskaitos darbo laiko režimas'),
    ('lankstus', 'Lankstaus darbo laiko režimas'),
    ('suskaidytos', 'Suskaidytos darbo dienos laiko režimas'),
    ('individualus', 'Individualus darbo laiko režimas')
]


def get_attendances(etatas, six_day_work_week=False):
    result = [(5,)]
    days_per_week = 5.0 if not six_day_work_week else 6.0
    hours_day = etatas * FULL_ETATAS_WEEKLY_HOURS / days_per_week  # P3:DivOK
    days = ['Pirmadienis', 'Antradienis', 'Trečiadienis', 'Ketvirtadienis', 'Penktadienis']
    if six_day_work_week:
        days.append('Šeštadienis')
    for i, day in enumerate(days):
        vals1 = {'name': day,
                 'dayofweek': str(i),
                 'hour_from': 8.00,
                 'hour_to': 8.00 + hours_day}
        result.extend([(0, 0, vals1)])
    return result


def get_default_attendances(start_at_9_am=False):
    result = [(5,)]
    days = ['Pirmadienis', 'Antradienis', 'Trečiadienis', 'Ketvirtadienis', 'Penktadienis']
    for dayofweek, day in enumerate(days):
        weekday_vals = {'name': day, 'dayofweek': str(dayofweek)}
        vals1 = weekday_vals.copy()
        vals1.update({'hour_from': 8.00 if not start_at_9_am else 9.00, 'hour_to': 12.00})
        vals2 = weekday_vals.copy()
        vals2.update({'hour_from': 13.00, 'hour_to': 17.00 if not start_at_9_am else 18.00})
        result.extend([(0, 0, vals1), (0, 0, vals2)])
    return result


def merge_time_ranges(time_ranges):
    time_ranges.sort()
    merged_ranges = list()
    i = 0
    while i < len(time_ranges):
        time_range = time_ranges[i]
        start, end = time_range
        last = (i >= len(time_ranges) - 1)
        while not last:
            next_time_range = time_ranges[i + 1]
            if end >= next_time_range[0]:
                end = next_time_range[1]
                i += 1
                last = (i >= len(time_ranges) - 1)
            else:
                break
        merged_ranges.append((start, end))
        i += 1
    return merged_ranges


def time_cross_constraints(time_ranges):
    if len(time_ranges) > 1:
        time_ranges.sort()
        if any(time_ranges.count(time_range) > 1 for time_range in time_ranges):
            raise exceptions.UserError(_('There can not be duplicate times'))
        time_ranges = list(set(time_ranges))
        for time_range in time_ranges:
            for l in time_ranges:
                if l == time_range:
                    continue
                if (l[0] <= time_range[0] < l[1]) or (time_range[0] <= l[0] < time_range[1]):
                    raise exceptions.UserError(_('Times can not cross'))


def split_time_range_into_day_and_night_times(time_from, time_to):
    night_start_of_day_start, night_start_of_day_end = min(time_from, NIGHT_SHIFT_END), min(time_to,
                                                                                            NIGHT_SHIFT_END)
    day_start, day_end = max(night_start_of_day_end, time_from), min(NIGHT_SHIFT_START, time_to)
    night_end_of_day_start, night_end_of_day_end = max(NIGHT_SHIFT_START, time_from), max(time_to,
                                                                                          NIGHT_SHIFT_START)
    night_times = list()
    day_times = list()
    if tools.float_compare(night_start_of_day_start, night_start_of_day_end, precision_digits=2) < 0:
        night_times.append((night_start_of_day_start, night_start_of_day_end))
    if tools.float_compare(night_end_of_day_start, night_end_of_day_end, precision_digits=2) < 0:
        night_times.append((night_end_of_day_start, night_end_of_day_end))
    if tools.float_compare(day_start, day_end, precision_digits=2) < 0:
        day_times.append((day_start, day_end))
    return {
        'day': day_times,
        'night': night_times
    }


def time_duration(time_ranges):
    total_duration = 0.0
    for time_range in time_ranges:
        time_range_duration = max(time_range[1] - time_range[0], 0.0)
        total_duration += time_range_duration
    return total_duration


def hours_to_hours_and_minutes(hours):
    hours, minutes = divmod(hours * 60, 60)
    hours, minutes = int(round(hours)), int(round(minutes))
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return hours, minutes


def hours_and_minutes_to_hours(hours, minutes):
    return hours + minutes / 60.0  # P3:DivOK


def add_minutes(hours, minutes_to_add=None):
    return hours + minutes_to_add / 60.0  # P3:DivOK


class ScheduleTemplate(models.Model):
    _name = 'schedule.template'
    _inherit = ['mail.thread']

    name = fields.Char(string='Pavadinimas', compute='_compute_name', store=True)
    name_translatable = fields.Char(string='Name that can be translatable', compute='_compute_name_translatable')

    template_type = fields.Selection(SCHEDULE_TEMPLATE_TYPES, string='Darbo laiko režimas', default='fixed',
                                     required=True, track_visibility='onchange')

    six_day_work_week = fields.Boolean(string='Šešių darbo dienų savaitė', compute='_compute_six_day_work_week')

    work_week_type = fields.Selection(
        [
            ('five_day', _('Penkias (Pir-Pen)')),
            ('six_day', _('Šešias (Pir-Šeš)')),
            ('based_on_template', _('Pagal darbo grafiko šabloną')),
        ],
        string='Kiek dienų trunka darbo savaitė',
        required=True,
        default='five_day',
        inverse='_inverse_update_related_models',
        track_visibility='onchange',
        compute='_compute_work_week_type',
        store=True
    )

    num_week_work_days = fields.Integer(compute='_compute_num_week_work_days')

    wage_calculated_in_days = fields.Boolean(string='Atlyginimas skaičiuojamas dienomis', default=True,
                                             inverse='_inverse_update_related_models', track_visibility='onchange')

    shorter_before_holidays = fields.Boolean(string='Trumpinti prieš šventes', default=True,
                                             inverse='_inverse_update_related_models', track_visibility='onchange')

    avg_hours_per_day = fields.Float(string='Apytikslis valandų skaičius per dieną', compute='_avg_hours_per_day')

    appointment_id = fields.Many2one('hr.contract.appointment', string='Darbo sutarties priedas', required=False,
                                     inverse='_inverse_update_related_models')

    fixed_attendance_ids = fields.One2many('fix.attendance.line', 'schedule_template_id', string='Grafikas', copy=True)

    struct_name = fields.Char(compute='_compute_struct_name')

    employee_id = fields.Many2one('hr.employee', related='appointment_id.employee_id')

    etatas = fields.Float(string='Etato dalis', compute='_compute_etatas', digits=(16, 5))

    etatas_stored = fields.Float(
        string='Etato dalis',
        required=False,
        default=1.0,
        digits=(16, 5),
        copy=True,
        inverse='_inverse_update_related_models',
        track_visibility='onchange',
        oldname='etatas'
    )

    max_monthly_hours = fields.Float(
        string='Darbo valandų per mėnesį',
        default=0.0,
        copy=True,
        inverse='_inverse_update_related_models',
        track_visibility='onchange'
    )

    work_norm = fields.Float(
        string='Darbo normos koeficientas (pagal profesiją)',
        default=1.0,
        required=True,
        inverse='_inverse_update_related_models',
        track_visibility='onchange'
    )

    men_constraint = fields.Selection(
        [('etatas', 'Etatas'), ('val_per_men', 'Valandų skaičius per mėn.')],
        string='Priskaičiavimas pagal etatą/valandų sk.',
        default='etatas',
        copy=True,
        inverse='_inverse_update_related_models',
        track_visibility='onchange'
    )

    @api.multi
    @api.depends('etatas_stored', 'max_monthly_hours', 'men_constraint', 'six_day_work_week')
    def _compute_etatas(self):
        for rec in self:
            if rec.men_constraint == 'etatas':
                rec.etatas = rec.etatas_stored
            else:
                avg_hours_per_day = rec.avg_hours_per_day
                # Check if average hours per day is set
                if tools.float_is_zero(avg_hours_per_day, precision_digits=2):
                    # Compute current month dates
                    now = datetime.utcnow()
                    date_from = (now + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to = (now + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                    # Get standard work hours for current month
                    hours_in_current_month = self.env['hr.payroll'].sudo().standard_work_time_period_data(
                        date_from, date_to, six_day_work_week=rec.six_day_work_week
                    ).get('hours', 0.0)

                    # Compute post from hours in current month and maximum monthly hours
                    rec.etatas = rec.max_monthly_hours / float(hours_in_current_month)  # P3:DivOK
                else:
                    rec.etatas = avg_hours_per_day / 8.0  # P3:DivOK

    @api.multi
    @api.depends('template_type', 'fixed_attendance_ids')
    def _compute_work_week_type(self):
        for rec in self:
            if rec.template_type not in ['fixed', 'suskaidytos']:
                rec.work_week_type = 'five_day'
            else:
                weekdays = rec.fixed_attendance_ids.mapped('dayofweek')
                weekdays = set([int(weekday) for weekday in weekdays])
                if len(weekdays) == 5 and all(x in weekdays for x in range(0, 5)):
                    rec.work_week_type = 'five_day'
                elif len(weekdays) == 6 and all(x in weekdays for x in range(0, 6)):
                    rec.work_week_type = 'six_day'
                else:
                    rec.work_week_type = 'based_on_template'

    @api.one
    @api.depends('appointment_id.struct_id')
    def _compute_struct_name(self):
        self.struct_name = self.appointment_id.struct_id.code

    @api.multi
    @api.constrains('fixed_attendance_ids', 'work_week_type')
    def _check_fixed_attendance_ids_set_when_based_on_schedule(self):
        for rec in self:
            if rec.work_week_type == 'based_on_template' and not rec.fixed_attendance_ids:
                raise exceptions.UserError(
                    _('Nustatant naudoti darbo dienų savaitę pagal grafiką, privaloma užpildyti grafiką')
                )

    @api.multi
    @api.constrains('etatas_stored', 'fixed_attendance_ids', 'template_type', 'work_norm', 'men_constraint')
    def _check_etatas_match_fixed_attendance_ids(self):
        for rec in self:
            if rec.template_type in ['fixed', 'suskaidytos'] and rec.men_constraint == 'etatas':
                fixed_attendance_id_time_sum = sum(rec.fixed_attendance_ids.mapped('time_total'))
                # P3:DivOK
                etatas_based_on_fixed_attendance_ids = fixed_attendance_id_time_sum / FULL_ETATAS_WEEKLY_HOURS
                etatas_diff = abs(etatas_based_on_fixed_attendance_ids - rec.etatas * rec.work_norm)
                if tools.float_compare(
                        etatas_diff, ETATAS_HALF_STEP, precision_digits=ETATAS_CHECK_PRECISION_DIGITS) >= 0:
                    raise exceptions.UserError(_('Etatas turi sutapti su grafiko darbo laiku'))

    @api.one
    @api.onchange('fixed_attendance_ids', 'template_type', 'men_constraint')
    def set_default_fixed_attendances(self):
        if self.template_type in ['fixed', 'suskaidytos'] and self.men_constraint == 'etatas':
            work_time_sum = sum(self.fixed_attendance_ids.mapped('time_total'))
            self.etatas_stored = work_time_sum / FULL_ETATAS_WEEKLY_HOURS  # P3:DivOK

    @api.one
    @api.depends('appointment_id', 'fixed_attendance_ids', 'etatas_stored', 'max_monthly_hours', 'work_norm',
                 'men_constraint')
    def _compute_name(self):
        if not self.name:
            employee_name = self.appointment_id.employee_id.display_name if self.appointment_id else False
            name_string = ''
            if employee_name:
                name_string = '%s' % employee_name
            if self.men_constraint == 'etatas':
                name_string += ', {:.3f} etato'.format(self.etatas)
            else:
                name_string += ', {:.3f} val./mėn.'.format(self.max_monthly_hours)
            name_string += ', {:.3f} darbo norma'.format(self.work_norm)
            if self.fixed_attendance_ids:
                days_per_week = len(set(self.fixed_attendance_ids.mapped('dayofweek')))
                name_string += ', %d d./sav.' % days_per_week
            self.name = name_string

    @api.depends('appointment_id', 'fixed_attendance_ids', 'etatas_stored', 'max_monthly_hours', 'work_norm',
                 'men_constraint')
    def _compute_name_translatable(self):
        for rec in self:
            if not rec.name_translatable:
                employee_name = rec.appointment_id.employee_id.display_name if rec.appointment_id else False
                name_string = employee_name or str()
                if rec.men_constraint == 'etatas':
                    name_string += _(', {:.3f} etato').format(rec.etatas)
                else:
                    name_string += _(', {:.3f} val./mėn.').format(rec.max_monthly_hours)
                name_string += _(', {:.3f} darbo norma').format(rec.work_norm)
                if rec.fixed_attendance_ids:
                    days_per_week = len(set(rec.fixed_attendance_ids.mapped('dayofweek')))
                    name_string += _(', %d d./sav.') % days_per_week
                rec.name_translatable = name_string

    @api.multi
    @api.constrains('etatas_stored', 'men_constraint', 'max_monthly_hours')
    def _check_men_constraint_values_are_given(self):
        for rec in self:
            if rec.men_constraint == 'etatas':
                if tools.float_is_zero(rec.etatas_stored, precision_digits=2):
                    raise exceptions.ValidationError(_('Nenustatyta etato dalis'))
            else:
                if tools.float_is_zero(rec.max_monthly_hours, precision_digits=2):
                    raise exceptions.ValidationError(_('Nenustatytas įprastas valandų skaičius per mėnesį'))

    @api.multi
    @api.constrains('etatas_stored', 'men_constraint')
    def _check_etatas(self):
        for rec in self:
            if rec.men_constraint == 'etatas' and not 0 < rec.etatas_stored <= 1.5:
                raise exceptions.UserError(_('Etato dalis turi būti tarp 0 ir 1.5'))

    @api.multi
    @api.constrains('work_norm')
    def _check_work_norm(self):
        for rec in self:
            if not 0 < rec.work_norm <= 1:
                raise exceptions.UserError(_('Darbo normos koeficientas turi būti tarp 0 ir 1'))

    @api.multi
    @api.constrains('max_monthly_hours', 'men_constraint')
    def _check_max_monthly_hours(self):
        for rec in self:
            if rec.men_constraint == 'val_per_men' and not 0 < rec.max_monthly_hours < 300:
                # 300 random value, max I think is 180 per month regular schedule, to be safe lets say there's never
                # gonna be more than 200 per month * 1.5 (max etatas) = 300
                raise exceptions.UserError(_('Valandų skaičiuos per mėnesį turi būti tarp 0 ir 300'))

    @api.one
    def _inverse_update_related_models(self):
        app = self.appointment_id
        if app:
            domain = [
                ('contract_id', '=', app.contract_id.id),
                ('date_to', '>=', app.date_start)
            ]
            if app.date_end:
                domain.append(
                    ('date_from', '<=', app.date_end)
                )
            ziniarastis_period_lines = self.env['ziniarastis.period.line'].search(domain)
            ziniarastis_period_lines._num_regular_work_days_contract_only()
            ziniarastis_period_lines.mapped('ziniarastis_day_ids')._compute_shorter_before_holidays_special()
            ziniarastis_period_lines._compute_num_regular_work_hours_without_holidays()

    @api.multi
    @api.depends('work_week_type')
    def _compute_six_day_work_week(self):
        for rec in self:
            rec.six_day_work_week = rec.work_week_type == 'six_day'

    @api.one
    @api.depends('work_week_type', 'fixed_attendance_ids')
    def _compute_num_week_work_days(self):
        if self.work_week_type == 'six_day':
            self.num_week_work_days = 6
        elif self.work_week_type == 'based_on_template':
            num_week_work_days = len(list(set(self.mapped('fixed_attendance_ids').filtered(
                lambda l: tools.float_compare(l.hour_from, l.hour_to, precision_digits=2) < 0).mapped('dayofweek'))))
            if tools.float_is_zero(num_week_work_days, precision_digits=2):
                num_week_work_days = 5
            self.num_week_work_days = num_week_work_days
        else:
            self.num_week_work_days = 5

    @api.multi
    def off_days(self):
        self.ensure_one()
        weekdays = [day for day in range(0, 7)]
        work_week_types = {
            'six_day': [day for day in range(0, 6)],
            'based_on_template': [int(dayofweek) for dayofweek in
                                  list(
                                      set(
                                          self.mapped('fixed_attendance_ids')
                                              .filtered(lambda l: tools.float_compare(l.hour_from, l.hour_to, precision_digits=2) < 0)
                                              .mapped('dayofweek')
                                         )
                                      )
                                  ]
        }
        schedule_weekdays = work_week_types.get(self.work_week_type, [day for day in range(0, 5)])
        schedule_off_days = list(set(weekdays) - set(schedule_weekdays))
        return schedule_off_days

    @api.multi
    def work_times_by_fixed_attendance_line_ids(self, date, skip_holidays=True, shorten_before_holidays=True):
        self.ensure_one()
        if isinstance(date, datetime):
            date_dt = date
            date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

        weekday = date_dt.weekday()

        fixed_attendance_ids = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(weekday))
        if not fixed_attendance_ids:
            return

        off_days = self.off_days()
        if weekday in off_days:
            return

        next_day_dt = date_dt + relativedelta(days=1)
        next_day = next_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        national_holiday_dates = self.env['sistema.iseigines'].search([('date', 'in', [date, next_day])]).mapped('date')

        if skip_holidays and date in national_holiday_dates:
            return

        shorter_day = shorten_before_holidays and self.shorter_before_holidays and next_day in national_holiday_dates

        total_schedule_time = sum(fixed_attendance_ids.mapped('time_total'))

        if shorter_day and tools.float_compare(total_schedule_time, 1.0, precision_digits=2) <= 0:
            return

        schedule_times = [(l.hour_from, l.hour_to) for l in fixed_attendance_ids]

        if shorter_day:
            time_to_shorten = 1.0
            schedule_times.sort(key=lambda t: t[0], reverse=True)
            adjusted_times = []
            for schedule_time in schedule_times:
                time_from = schedule_time[0]
                time_to = schedule_time[1]
                duration = time_to - time_from
                shorten_by = min(duration, time_to_shorten)
                if tools.float_compare(duration, shorten_by, precision_digits=2) <= 0:
                    time_to_shorten -= duration
                    time_to_shorten = max(time_to_shorten, 0.0)
                else:
                    adjusted_times.append((time_from, time_to - time_to_shorten))
            schedule_times = adjusted_times
            schedule_times.sort(key=lambda t: t[0])

        return schedule_times

    @api.multi
    def open_default_schedule_template_setter(self):
        action = self.env.ref('l10n_lt_payroll.schedule_value_reset_action').read()[0]
        action['context'] = {'schedule_template_id': self.id,
                             'start_at_9_am': self._context.get('start_at_9_am', False)}
        return action

    @api.multi
    @api.constrains('template_type', 'fixed_attendance_ids')
    def _check_fixed_attendance_ids_exist(self):
        for rec in self:
            if rec.template_type in ['fixed', 'suskaidytos'] and len(rec.mapped('fixed_attendance_ids.id')) < 1:
                raise exceptions.ValidationError(
                    _('Nekintančio darbo laiko grafikas privalo turėti bent vieną grafiko eilutę')
                )

    @api.one
    def set_regular_schedule_values(self, start_at_9_am=False):
        if not self:
            return
        self.write({
            'template_type': 'fixed',
            'fixed_attendance_ids': get_default_attendances(start_at_9_am),
            'etatas_stored': 1.0,
            'wage_calculated_in_days': True,
        })

    @api.one
    @api.depends('six_day_work_week', 'etatas_stored')
    def _avg_hours_per_day(self):
        workdays_per_week = float(self.num_week_work_days)
        if self.men_constraint == 'etatas':
            weekly_hours = self.etatas * FULL_ETATAS_WEEKLY_HOURS * self.work_norm
            if not weekly_hours or tools.float_is_zero(weekly_hours, precision_digits=2):
                weekly_hours = FULL_ETATAS_WEEKLY_HOURS
            self.avg_hours_per_day = weekly_hours / workdays_per_week  # P3:DivOK
        else:
            time_total = sum(self.fixed_attendance_ids.mapped('time_total'))
            if tools.float_is_zero(time_total, precision_digits=2):
                self.avg_hours_per_day = (self.max_monthly_hours or 0.0) / 31.0  # P3:DivOK
            else:
                try:
                    time_total = sum(self.fixed_attendance_ids.mapped('time_total'))
                    self.avg_hours_per_day = time_total / self.num_week_work_days  # P3:DivOK
                except ZeroDivisionError:
                    self.avg_hours_per_day = (self.max_monthly_hours or 0.0) / 31.0  # P3:DivOK

    def num_work_days(self, date_from, date_to):
        if date_from > date_to:
            return 0
        date_start = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        res = 0
        while date_start <= date_end:
            date_s = date_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if self.is_work_day(date_s):
                res += 1
            date_start += relativedelta(days=1)
        return res

    @api.onchange('etatas_stored', 'template_type')
    def set_default_fixed_attendances(self):
        if self.template_type in ['fixed', 'suskaidytos']:
            self.fixed_attendance_ids = get_attendances(self.etatas, self.six_day_work_week)

    @api.onchange('etatas_stored', 'template_type')
    def set_wage_calculated_in_days(self):
        etatas_is_one = tools.float_compare(self.etatas, 1.0, precision_digits=2) == 0
        is_monthly = self.struct_name == 'MEN' or not self.struct_name
        if self.template_type not in ['fixed', 'suskaidytos'] or not is_monthly or not etatas_is_one:
            self.wage_calculated_in_days = False
        else:
            self.wage_calculated_in_days = True

    @api.multi
    def is_work_day(self, date_str):
        self.ensure_one()
        is_public_holiday = self.env['sistema.iseigines'].search_count([('date', '=', date_str)]) > 0
        if self.template_type not in ['fixed', 'suskaidytos']:
            # These types don't have specific times (fixed_attendance_ids) for dates
            calculating_holidays = self._context.get('calculating_holidays', False)
            calculating_before_holidays = self._context.get('calculating_before_holidays', False)
            do_not_use_ziniarastis = self._context.get('do_not_use_ziniarastis', False)
            force_use_schedule_template = self._context.get('force_use_schedule_template', False)
            if calculating_holidays and is_public_holiday:
                return False
            if force_use_schedule_template:
                return True
            if calculating_holidays and not do_not_use_ziniarastis:
                ziniarastis_line = self.env['ziniarastis.period.line'].search([
                    ('contract_id', '=', self.appointment_id.contract_id.id),
                    ('date_from', '<=', date_str),
                    ('date_to', '>=', date_str)
                ], limit=1)
                if not ziniarastis_line:
                    return True
                else:
                    ziniarastis_day = ziniarastis_line.ziniarastis_day_ids.filtered(lambda d: d.date == date_str)
                    worked_time_hours = sum(ziniarastis_day.mapped('ziniarastis_day_lines.worked_time_hours'))
                    worked_time_minutes = sum(ziniarastis_day.mapped('ziniarastis_day_lines.worked_time_minutes'))
                    return bool(worked_time_hours + worked_time_minutes)
            return True
        else:
            if is_public_holiday:
                return False
            weekday = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
            related_schedule_lines = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(weekday))
            return bool(related_schedule_lines)

    @api.multi
    def get_regular_hours(self, date):
        self.ensure_one()
        if not self.is_work_day(date):
            return 0
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        next_date = (date_dt + timedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        public_holiday_dates = self.env['sistema.iseigines'].search([('date', 'in', [date, next_date])]).mapped('date')
        next_day_is_public_holiday = next_date in public_holiday_dates
        total_hours = 0.0
        if self.template_type not in ['fixed', 'suskaidytos'] and not self._context.get('calculating_work_norm', False):
            total_hours = self.avg_hours_per_day
        else:
            # Only employees working by accumulative work time accounting should be working on holiday days, otherwise
            # an agreement is needed.
            if date not in public_holiday_dates or self.template_type == 'sumine':
                weekday = date_dt.weekday()
                related_schedule_lines = self.fixed_attendance_ids.filtered(lambda r: r.dayofweek == str(weekday))
                total_hours = sum(l.time_total for l in related_schedule_lines)
        if next_day_is_public_holiday and self.shorter_before_holidays and not self._context.get('calculating_work_norm', False):
            total_hours -= 1.0
        return max(total_hours, 0.0)

    @api.multi
    def _get_regular_work_times(self, dates):
        """
        Gets regular work times based on schedule lines.
        Args:
            dates (list): dates to get for

        Returns: a dict of all the work times split by day and night times

        """
        res = defaultdict(dict)
        if not dates or not self.mapped('appointment_id'):
            return dict(res)

        dates = list(dates)

        min_date, max_date = min(dates), max(dates)
        max_date_dt = datetime.strptime(max_date, tools.DEFAULT_SERVER_DATE_FORMAT)

        regular_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        remote_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_NT')
        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')

        dates_before_holidays = self.env['sistema.iseigines'].get_dates_with_shorter_work_date(min_date, max_date)

        for rec in self:
            res[rec.id] = dict()
            off_days = rec.off_days()
            average_hours_per_day = rec.avg_hours_per_day

            accumulative_work_time_accounting = rec.template_type == 'sumine'
            can_work_on_holidays = accumulative_work_time_accounting

            time_to_shorten_by_date = dict()
            next_day_after_max = None
            if rec.shorter_before_holidays:
                next_day_after_max = (max_date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                dates.append(next_day_after_max)  # Used for shorter before holidays. Removed from res later.

            weekly_scheduled_attendances = rec.fixed_attendance_ids

            for date in dates:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                weekday = date_dt.weekday()

                date_before_holidays = date in dates_before_holidays

                time_to_shorten = time_to_shorten_by_date.get(date, 0.0)

                if date_before_holidays and rec.shorter_before_holidays:
                    # Shorten the end work time for the day if it's a shorter day
                    time_to_shorten += 1.0

                    if can_work_on_holidays:
                        # Get data for the holiday date
                        holiday_date_dt = date_dt + relativedelta(days=1)
                        holiday_date = holiday_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        holiday_date_weekday = holiday_date_dt.weekday()
                        holiday_date_schedule_lines = weekly_scheduled_attendances.filtered(
                            lambda l: l.dayofweek == str(holiday_date_weekday)
                        )
                        holiday_date_shift_starts_at_midnight = holiday_date_schedule_lines and any(
                            tools.float_is_zero(holiday_line.hour_from, precision_digits=2) and
                            not tools.float_is_zero(holiday_line.hour_to, precision_digits=2)
                            for holiday_line in holiday_date_schedule_lines
                        )

                        # If there's a shift planned at midnight for the holiday date then simply shorten the end time
                        # of the holiday work time
                        if holiday_date_shift_starts_at_midnight:
                            holiday_date_time_to_shorten = time_to_shorten_by_date.get(holiday_date, 0.0)
                            holiday_date_duration = sum(line.hour_to - line.hour_from for line in holiday_date_schedule_lines)
                            to_shorten = min(holiday_date_duration, time_to_shorten)
                            time_to_shorten -= to_shorten
                            time_to_shorten_by_date[holiday_date] = to_shorten + holiday_date_time_to_shorten

                weekday_lines = weekly_scheduled_attendances.filtered(lambda l: l.dayofweek == str(weekday))
                if weekday_lines:
                    day_working_ranges = [
                        (
                            line.hour_from,
                            line.hour_to,
                            remote_work_marking.id if line.working_remotely else regular_work_marking.id
                        ) for line in weekday_lines
                    ]
                    day_working_ranges.sort(key=lambda time: time[0], reverse=True)
                elif not weekly_scheduled_attendances and accumulative_work_time_accounting and weekday not in off_days:
                    time_from, time_to = DEFAULT_SCHEDULE_START, min(DEFAULT_SCHEDULE_START + average_hours_per_day, 24.0)
                    day_working_ranges = [(time_from, time_to, regular_work_marking.id)]
                else:
                    day_working_ranges = list()

                day_lines = list()
                night_lines = list()

                for working_range in day_working_ranges:
                    time_from = working_range[0]
                    time_to = working_range[1]
                    marking = working_range[2]
                    duration = max(time_to - time_from, 0.0)
                    if tools.float_compare(time_to_shorten, 0.0, precision_digits=2) > 0:
                        time_possible_to_shorten = min(duration, time_to_shorten)
                        time_to_shorten -= time_possible_to_shorten
                        if tools.float_compare(duration, time_possible_to_shorten, precision_digits=2) == 0:
                            continue
                        duration -= time_possible_to_shorten
                        duration = max(duration, 0.0)
                        time_to = time_from + duration
                    line_split_by_time_of_day = split_time_range_into_day_and_night_times(time_from, time_to)
                    daytime_lines = line_split_by_time_of_day.get('day', list())
                    daytime_lines = [(l[0], l[1], marking) for l in daytime_lines]  # Set marking
                    day_lines += daytime_lines
                    night_lines += line_split_by_time_of_day.get('night', list())

                day_line_markings = set(l[2] for l in day_lines)
                adjusted_lines = list()
                for day_line_marking in day_line_markings:
                    marking_lines = [(l[0], l[1]) for l in day_lines if l[2] == day_line_marking]
                    marking_lines = merge_time_ranges(marking_lines)
                    adjusted_lines += [(l[0], l[1], day_line_marking) for l in marking_lines]
                day_lines = adjusted_lines
                day_lines.sort(key=lambda l: l[0])
                night_lines = merge_time_ranges(night_lines)
                night_lines = [(l[0], l[1], working_nights_marking.id) for l in night_lines]

                res[rec.id][date] = {
                    'day_duration': time_duration(day_lines),
                    'night_duration': time_duration(night_lines),
                    'day_lines': day_lines,
                    'night_lines': night_lines,
                }

            if next_day_after_max:
                # Added manually for shorter before holidays. Not in the original dates list
                res[rec.id].pop(next_day_after_max)
                dates.remove(next_day_after_max)

        return dict(res)

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
        downtime_schedule = list()

        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')
        regular_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        downtime_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_PN')

        holiday = downtime_object.holiday_id
        if not holiday or not holiday.date_from_date_format <= date <= holiday.date_to_date_format:
            day_lines = regular_work_times.get('day_lines', list())
            night_lines = regular_work_times.get('night_lines', list())
            return day_lines + night_lines  # Return the regular schedule since the day should not be downtime

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

            # Get the lines the employee should work if the day was not downtime
            day_lines = regular_work_times.get('day_lines', list())
            night_lines = regular_work_times.get('night_lines', list())
            # Set marking for those lines to be downtime
            day_lines = [(line[0], line[1], downtime_marking.id) for line in day_lines]
            night_lines = [(line[0], line[1], downtime_marking.id) for line in night_lines]

            # Add downtime lines to downtime schedule
            downtime_schedule = merge_line_values(downtime_schedule, day_lines)
            downtime_schedule = merge_line_values(downtime_schedule, night_lines)
        else:
            # Partial downtime
            if not downtime_object.employee_schedule_is_regular:
                # Figure out how much downtime should be set for the employee/schedule
                try:
                    # P3:DivOK
                    downtime_per_day = downtime_object.downtime_reduce_in_time / float(self.num_week_work_days)
                except ZeroDivisionError:
                    downtime_per_day = 0.0
                # Guess the hours the downtime should be set for and add them to the downtime schedule
                time_from, time_to = DEFAULT_SCHEDULE_START, min(DEFAULT_SCHEDULE_START + downtime_per_day, 24.0)
                downtime_schedule.append((time_from, time_to, regular_work_marking.id))
            else:
                # Get the downtime schedule for date and add it to the downtime schedule list
                downtime_schedule_lines = downtime_object.downtime_schedule_line_ids
                weekday = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
                date_downtime_schedule = downtime_schedule_lines.filtered(lambda s: int(s.weekday) == weekday)
                downtime_schedule += [(l.time_from, l.time_to, regular_work_marking.id) for l in date_downtime_schedule]

            # Fill the rest of the day with downtime work time since the downtime is partial
            day_lines = [(l[0], l[1], downtime_marking.id) for l in regular_work_times.get('day_lines', list())]
            night_lines = [(l[0], l[1], downtime_marking.id) for l in regular_work_times.get('night_lines', list())]

            # When adding regular work time to downtime time - don't set more than the planned regular. This is needed
            # when downtime is set during off hours, before or after the shift, or during the break.

            # Get the regular work time duration for the day
            regular_work_time_day_duration = sum(x[1] - x[0] for x in day_lines)
            regular_work_time_night_duration = sum(x[1] - x[0] for x in night_lines)

            # Get the downtime duration
            downtime_duration = sum(x[1] - x[0] for x in downtime_schedule)

            # Calculate the maximum amount of day time to set
            day_time_to_set = regular_work_time_day_duration - downtime_duration

            # Calculate the maximum amount of night time to set based on how much downtime has been deducted from the
            # day time
            night_time_to_set = 0.0
            if tools.float_compare(day_time_to_set, 0.0, precision_digits=2) < 0:
                # Only reduce night time if day time to set is negative, meaning that the downtime duration for day is
                # longer than the regular day time for the day.

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

        # Add empty line if no lines are set
        if not downtime_schedule:
            downtime_schedule = [(0.0, 0.0, downtime_marking.id)]

        return downtime_schedule

    @api.multi
    def _get_september_first_schedule(self, regular_work_times):
        self.ensure_one()

        september_first_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_MP')
        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')

        scheduled_day_lines = regular_work_times.get('day_lines', list())
        scheduled_night_lines = regular_work_times.get('night_lines', list())
        # Add working nights marking to night lines
        scheduled_night_lines = [(l[0], l[1], working_nights_marking.id) for l in scheduled_night_lines]
        scheduled_day_duration = regular_work_times.get('day_duration', 0.0)
        scheduled_night_duration = regular_work_times.get('night_duration', 0.0)
        scheduled_total_duration = scheduled_day_duration + scheduled_night_duration

        september_first_schedule = list()

        # P3:DivOK
        time_off = scheduled_total_duration / 2.0  # Time that is of on September first
        for line in scheduled_day_lines + scheduled_night_lines:
            if tools.float_compare(time_off, 0.0, precision_digits=2) <= 0:
                # No more time off, just use the regular work time
                september_first_schedule.append(line)
                continue
            max_to_set = line[1] - line[0]
            if tools.float_compare(max_to_set, time_off, precision_digits=2) > 0:
                # Able to set more time free on a single line than it is needed (split line)
                try:
                    marking_to_use = line[2]
                except IndexError:
                    marking_to_use = None
                # Set the time off
                september_first_schedule.append((line[0], line[0] + time_off, september_first_marking.id))
                # Split the line and set the other time as time worked
                september_first_schedule.append((line[0] + time_off, line[1], marking_to_use))
                time_off = 0.0  # No more time off is needed
            else:
                # Set time off
                september_first_schedule.append((line[0], line[1], september_first_marking.id))
                time_off -= line[1] - line[0]
        return september_first_schedule

    @api.model
    def _set_time_ranges_as_overtime(self, time_ranges):
        overtime_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DP')
        working_nights_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')
        overtime_time_ranges = []
        for time_range in time_ranges:
            time_from, time_to = time_range[0], time_range[1]
            try:
                marking = time_range[2]
            except IndexError:
                marking = None
            if marking == working_nights_marking.id:
                marking = overtime_marking.id  # TODO overtime night hours? We don't have a code for this as of now
            else:
                marking = overtime_marking.id
            overtime_time_ranges.append((time_from, time_to, marking))
        return overtime_time_ranges

    @api.multi
    def _get_planned_time_ranges(self, dates):
        def find_regular_work_times_by_duration(duration, regular_template_times):
            """ Finds a day in regular work time dates with the requested duration """
            suitable_times = list()
            for regular_work_time in regular_template_times.values():
                line_work_time_total = sum(l[1] - l[0] for l in regular_work_time.get('day_lines', list()))
                if tools.float_compare(line_work_time_total, duration, precision_digits=2) == 0:
                    suitable_times = list(regular_work_time['day_lines'])
                    break
            return suitable_times

        res = {}
        if not dates:
            return res

        regular_work_times = self._get_regular_work_times(dates)

        min_date, max_date = min(dates), max(dates)

        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '>=', min_date), ('date', '<=', max_date)]
        ).mapped('date')

        employees = self.mapped('appointment_id.employee_id')

        hr_holidays = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', max_date),
            ('date_to_date_format', '>=', min_date),
            ('state', '=', 'validate'),
            ('employee_id', 'in', employees.ids)
        ])

        downtime_objects = self.env['hr.employee.downtime'].search([('holiday_id', 'in', hr_holidays.ids)])

        regular_work_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        september_first_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_MP')
        downtime_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_PN')
        working_outside_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DLS')
        business_trip_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_K')

        dynamic_workplace_compensations_lines = self.env['hr.employee.compensation.time.line'].search([
            ('compensation_id.compensation_type', '=', 'dynamic_workplace'),
            ('compensation_id.compensation_time_ids', '!=', False),
            ('compensation_id.state', '=', 'confirm'),
            ('compensation_id.date_from', '<=', max_date),
            ('compensation_id.date_to', '>=', min_date),
            ('compensation_id.employee_id', 'in', employees.ids),
            ('date', '>=', min_date),
            ('date', '<=', max_date)
        ])

        forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date', '<=', max_date),
            ('date', '>=', min_date)
        ])

        overtime_lines = self.env['hr.employee.overtime.time.line'].search([
            ('overtime_id.employee_id', 'in', employees.ids),
            ('date', 'in', dates),
            ('overtime_id.state', '=', 'confirmed'),
        ])

        for template in self:
            employee = template.appointment_id.employee_id
            template_regular_work_times = regular_work_times.get(template.id, dict())
            extra_business_trip_dates = list()
            employee_id = employee.id if employee else None
            if employee_id:
                extra_business_trip_dates = self.env['hr.holidays'].get_extra_business_trip_dates(employee_id, dates)

            employee_dynamic_workplace_compensations_lines = dynamic_workplace_compensations_lines.filtered(
                lambda l: l.compensation_id.employee_id.id == employee_id
            )
            employee_overtime_lines = overtime_lines.filtered(lambda l: l.overtime_id.employee_id.id == employee_id)

            res[template.id] = dict()

            for date in dates:
                # Lines to set
                date_lines_to_set = list()

                # Check for forced work times. These times can only be set by accountants manually and they override
                # everything. Main purpose is to set time that the employee has worked while he was on sick pay so that
                # the SoDra bots detecting a leave do not override these work times.
                forced_date_work_times = forced_work_times.filtered(lambda t: t.employee_id == employee and
                                                                              t.date == date)
                if forced_date_work_times:
                    res[template.id][date] = [(t.time_from, t.time_to, t.marking_id.id) for t in forced_date_work_times]
                    continue

                # Get what is schedule by the schedule template on that date including shorter before holidays
                scheduled_work_times = template_regular_work_times.get(date, dict())
                scheduled_day_lines = scheduled_work_times.get('day_lines', list())
                scheduled_night_lines = scheduled_work_times.get('night_lines', list())
                scheduled_regular_lines = scheduled_day_lines + scheduled_night_lines

                # Get holiday record for date
                hr_holiday = hr_holidays.filtered(
                    lambda holiday: holiday.date_from_date_format <= date <= holiday.date_to_date_format and
                                    holiday.employee_id == employee
                )
                if len(hr_holiday) > 1:
                    hr_holiday = hr_holiday.filtered(lambda h: h.contract_id == template.appointment_id.contract_id)
                hr_holiday = hr_holiday and hr_holiday[0]

                is_national_holiday = date in national_holiday_dates

                date_overtime_lines = employee_overtime_lines.filtered(lambda l: l.date == date)
                overtime_times = date_overtime_lines.get_formatted_times([date] if is_national_holiday else list())

                if is_national_holiday:
                    # Skip setting the time if the day is a national holiday and the employee doesn't work on holidays
                    marking = hr_holiday.holiday_status_id.tabelio_zymejimas_id if hr_holiday else regular_work_marking
                    scheduled_regular_lines = [(0.0, 0.0, marking.id)]

                if hr_holiday:
                    holiday_marking = hr_holiday.holiday_status_id.tabelio_zymejimas_id
                    if holiday_marking == september_first_marking:
                        # Special case for september first
                        date_lines_to_set += template._get_september_first_schedule(scheduled_work_times)
                    elif holiday_marking == downtime_marking and not is_national_holiday:
                        # Fill date times if the day is downtime
                        downtime_object = downtime_objects.filtered(lambda x: x.holiday_id == hr_holiday)
                        downtime_schedule = template._get_downtime_schedule(downtime_object, date, scheduled_work_times)
                        downtime_lines = list()
                        other_lines = list()
                        for line in downtime_schedule:
                            try:
                                marking = line[2]
                            except IndexError:
                                marking = regular_work_marking.id
                            if marking == downtime_marking.id:
                                downtime_lines.append(line)
                            else:
                                other_lines.append(line)
                        schedule_to_set = downtime_lines
                        schedule_to_set = merge_line_values(schedule_to_set, overtime_times)
                        schedule_to_set = merge_line_values(schedule_to_set, other_lines)
                        date_lines_to_set += schedule_to_set
                    else:
                        # Set regular work time with the holiday code
                        marking_to_use = holiday_marking.id
                        if marking_to_use == business_trip_marking.id:
                            # If day is business trip set regular marking instead of holiday marking
                            marking_to_use = regular_work_marking.id
                        date_lines_to_set += overtime_times
                        if date in extra_business_trip_dates:
                            # Set overtime for dates worked during business trips
                            if not scheduled_regular_lines:
                                # No lines were scheduled - find some regular work times for some day that match the
                                # template average hours per day
                                scheduled_regular_lines = find_regular_work_times_by_duration(
                                    template.avg_hours_per_day, regular_work_times.get(template.id, dict())
                                )
                            if not scheduled_regular_lines:
                                scheduled_regular_lines = [(8.0, 8.0+template.avg_hours_per_day, regular_work_marking.id)]
                            scheduled_regular_lines = self._set_time_ranges_as_overtime(scheduled_regular_lines)
                            date_lines_to_set = merge_line_values(date_lines_to_set, scheduled_regular_lines)
                        elif scheduled_regular_lines:
                            marking_adjusted_regular_times = [(l[0], l[1], marking_to_use) for l in scheduled_regular_lines]
                            date_lines_to_set = merge_line_values(date_lines_to_set, marking_adjusted_regular_times)
                        elif not date_lines_to_set:
                            date_lines_to_set.append((0.0, 0.0, marking_to_use))  # Add empty line for display
                else:
                    schedule_for_date = list()

                    scheduled_regular_time_duration = sum(l[1] - l[0] for l in scheduled_regular_lines)
                    maximum_regular_time_to_set = scheduled_regular_time_duration

                    # Compensation time lines
                    date_dynamic_workplace_compensations_lines = employee_dynamic_workplace_compensations_lines.filtered(
                        lambda l: l.date == date
                    )
                    work_outside_lines = [
                        (l.time_from, l.time_to, working_outside_marking.id)
                        for l in date_dynamic_workplace_compensations_lines
                    ]
                    # Merge work outside lines with the current schedule
                    schedule_for_date = merge_line_values(schedule_for_date, work_outside_lines)

                    maximum_regular_time_to_set -= sum(l[1] - l[0] for l in work_outside_lines)

                    schedule_for_date = merge_line_values(schedule_for_date, overtime_times)

                    if date in extra_business_trip_dates:
                        scheduled_regular_lines = self._set_time_ranges_as_overtime(scheduled_regular_lines)

                    maximum_regular_time_to_set = max(maximum_regular_time_to_set, 0.0)

                    # Merge regular work time with the current schedule
                    schedule_for_date = merge_line_values(
                        schedule_for_date,
                        scheduled_regular_lines,
                        maximum_regular_time_to_set
                    )
                    date_lines_to_set += schedule_for_date

                fixed_date_lines = list()
                for date_line_to_set in date_lines_to_set:
                    # Set regular work marking on lines that don't have it set
                    time_from, time_to = date_line_to_set[0], date_line_to_set[1]
                    if time_from > time_to:
                        continue  # Remove incorrect times
                    elif tools.float_compare(time_from, time_to, precision_digits=2) == 0 and not hr_holiday:
                        continue  # Remove identical times
                    try:
                        marking_id = date_line_to_set[2]
                    except IndexError:
                        marking_id = regular_work_marking.id
                    fixed_date_lines.append((time_from, time_to, marking_id))

                res[template.id][date] = fixed_date_lines
        return res

    @api.multi
    def get_actual_hours(self, dates):
        """
            returns dict {template.id: {date: {zymejimas_id: (hour, minutes)}}}
        """
        res = {}
        if not dates:
            return res

        planned_time_ranges = self._get_planned_time_ranges(dates)
        for template in self:
            template_planned_time_ranges = planned_time_ranges.get(template.id, dict())
            res[template.id] = dict()
            for date in dates:
                date_planned_time_ranges = template_planned_time_ranges.get(date, list())
                date_times_by_code = {}
                for date_planned_time_range in date_planned_time_ranges:
                    time_from, time_to, marking_id = date_planned_time_range
                    time_range_duration = max(time_to - time_from, 0.0)
                    hours, minutes = date_times_by_code.get(marking_id, (0, 0))
                    total_marking_time = hours_and_minutes_to_hours(hours, minutes)
                    total_marking_time += time_range_duration
                    date_times_by_code[marking_id] = hours_to_hours_and_minutes(total_marking_time)
                res[template.id][date] = date_times_by_code
        return res

    @api.multi
    def get_working_ranges(self, dates):
        """
            returns dict {date: [(from, to)]}
        """
        self.ensure_one()
        res = {}
        if not dates:
            return res
        for date in dates:
            res[date] = []
        min_date = min(dates)
        max_date = max(dates)
        national_holidays = self.env['sistema.iseigines'].search(
            [('date', '>=', min_date), ('date', '<=', max_date)]).mapped('date')
        dates_with_shorter_work_date = self.env['sistema.iseigines'].get_dates_with_shorter_work_date(min_date,
                                                                                                      max_date)
        shorter_before_holidays = self.shorter_before_holidays
        regular_dates = [date for date in dates if date not in national_holidays]
        for date in regular_dates:
            weekday = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
            related_schedule_lines = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(weekday))
            if related_schedule_lines:
                last_end = max(related_schedule_lines.mapped('hour_to'))
                for l in related_schedule_lines.sorted(lambda r: r.hour_to):
                    latest_period = l.hour_to == last_end
                    hour_from = l.hour_from
                    hour_to = l.hour_to
                    if shorter_before_holidays and date in dates_with_shorter_work_date and latest_period:
                        hour_to -= 1
                        if hour_to < hour_from:
                            continue
                    res[date].append((hour_from, hour_to))
        return res

    @api.multi
    def is_time_range_during_work_hours(self, time_from, time_to, dayofweek):
        """
        Checks if the given range from time_from to time_to for a given dayofweek is completely during the working
        ranges for the schedule template
        @param time_from: float - time to check from
        @param time_to: float - time to check to
        @param dayofweek: int - weekday to check
        @return: boolean - is the time is in the working ranges for the day
        """
        self.ensure_one()
        if self.template_type not in ['fixed', 'suskaidytos']:
            return True  # Dynamic working times

        # Get related schedule lines by weekday
        related_schedule_lines = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(dayofweek)).sorted(
            key=lambda line: line.hour_from
        )
        if not related_schedule_lines:
            return False

        times = []
        hour_from = hour_to = None
        minute = 1.0 / 60.0  # P3:DivOK
        # Merge line times together
        for line in related_schedule_lines:
            if not hour_from:
                hour_from, hour_to = line.hour_from, line.hour_to
                continue
            current_line_hour_from = line.hour_from
            if tools.float_compare(hour_to + minute, current_line_hour_from, precision_digits=2) != 0:
                times.append((hour_from, hour_to))
                hour_from = current_line_hour_from
            hour_to = line.hour_to
        times.append((hour_from, hour_to))

        unaccounted_time = time_to - time_from
        if tools.float_compare(unaccounted_time, 0.0, precision_digits=2) < 0:  # Time to before time from
            return False
        if tools.float_is_zero(unaccounted_time, precision_digits=2):
            return True

        # Try to assign the unaccounted time to working ranges
        for time in times:
            if tools.float_compare(unaccounted_time, 0.0, precision_digits=2) <= 0:
                break
            start = max(time[0], min(time[1], time_from))
            end = min(time[1], max(time[0], time_to))
            if tools.float_compare(start, end, precision_digits=2) >= 0:
                continue
            unaccounted_time -= end-start

        return tools.float_compare(unaccounted_time, 0.0, precision_digits=2) <= 0


ScheduleTemplate()


class ScheduleTemplateAttendanceLine(models.Model):
    _name = 'fix.attendance.line'  # TODO Rename and make it more accurate (involves SQL queries to change table names)

    _description = "Work Schedule Detail"
    _order = 'dayofweek, hour_from'

    name = fields.Char(compute='_compute_name')
    schedule_template_id = fields.Many2one('schedule.template', string='Tvarkaraščio šablonas', ondelete='cascade')
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], string='Savaitės diena', required=True, index=True, default='0')
    hour_from = fields.Float(string='Dirbama nuo', required=True, index=True, help='Darbo pradžios laikas')
    hour_to = fields.Float(string='Dirbama iki', required=True, help='Darbo pabaigos laikas')
    working_remotely = fields.Boolean(string='Working remotely')
    time_total = fields.Float(string='Trukmė', compute='_compute_time_total')

    @api.multi
    @api.constrains('hour_from', 'hour_to')
    def _check_hour_from_is_smaller_than_hour_to(self):
        for rec in self:
            if rec.hour_from and rec.hour_to:
                if tools.float_compare(rec.hour_from, rec.hour_to, precision_digits=2) > 0:
                    raise exceptions.ValidationError(_('Dirbama nuo turi būti mažiau už dirbama iki'))

    @api.one
    @api.depends('hour_from', 'hour_to')
    def _compute_time_total(self):
        self.time_total = self.hour_to - self.hour_from

    @api.one
    @api.depends('dayofweek', 'hour_from', 'hour_to')
    def _compute_name(self):
        weekday = dict(self._fields['dayofweek']._description_selection(self.env)).get(self.dayofweek)
        self.name = '%s %s-%s' % (weekday, self.hour_from, self.hour_to)


ScheduleTemplateAttendanceLine()
