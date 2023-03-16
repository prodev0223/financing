# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _


class HrEmployeeDowntime(models.Model):
    _name = 'hr.employee.downtime'
    _description = 'Employee downtime'

    _inherits = {
        'hr.holidays': 'holiday_id',
    }

    holiday_id = fields.Many2one('hr.holidays', string="Neatvykimas", required=True, ondelete='cascade')

    state = fields.Selection([('draft', 'Juodraštis'), ('confirm', 'Patvirtinta')], string='Būsena', compute='_compute_state')

    downtime_type = fields.Selection(
        [('full', _('Viso darbo laiko')), ('partial', _('Dalinė'))],
        string='Prastovos tipas',
        default='full',
        required=True
    )

    downtime_subtype = fields.Selection(
        [('ordinary', _('Įprasta')), ('due_to_special_cases', _('Dėl ekstremalios padėties ar karantino'))],
        string='Prastovos subtipas',
        default='ordinary',
        required=True
    )

    reason = fields.Text(string='Priežastis')

    state_declared_emergency_id = fields.Many2one(
        'state.declared.emergency',
        string='Ekstremali padėtis ar karantinas'
    )

    downtime_schedule_line_ids = fields.One2many(
        'hr.employee.downtime.schedule.line',
        'hr_employee_downtime_id',
        relation='hr_employee_downtime_employee_downtime_schedule_rel',
        string='Grafikas prastovos laikotarpiu'
    )

    come_to_work_schedule_line_ids = fields.One2many(
        'hr.employee.downtime.schedule.line',
        'hr_employee_downtime_id',
        relation='hr_employee_downtime_employee_come_to_work_schedule_rel',
        string='Atvykimo į darbą grafikas'
    )

    pay_type = fields.Selection(
        [
            ('mma', _('Mokėti MMA, paskaičiuotą pagal darbo laiko normą')),
            ('salary', _('Mokėti darbuotojo darbo užmokesčio dalį neviršijančią 1,5 minimalaus mėnesinio atlyginimo')),
            ('custom', _('Įvesti'))
        ],
        string='Prastovos apmokėjimas',
        default='mma'
    )

    pay_amount = fields.Float(
        string='Prastovos išmokos dydis',
        help='Amount to be paid when the downtime is due quarantine or other extreme cases and the employee is not '
             'going to be paid the minimum wage'
    )

    downtime_reduce_in_time = fields.Float(
        string='Prastovos laikotarpiu sutrumpinamas darbo laikas (valandomis per savaitę)'
    )

    downtime_duration = fields.Integer(
        compute='_compute_downtime_duration'
    )

    downtime_weekly_hours = fields.Float(compute='_compute_downtime_weekly_time')
    downtime_weekly_days = fields.Integer(compute='_compute_downtime_weekly_time')

    employee_schedule_is_regular = fields.Boolean(
        compute='_compute_employee_schedule_is_regular'
    )

    possible_to_calculate_in_days = fields.Boolean(compute='_compute_possible_to_calculate_in_days')

    @api.multi
    @api.depends('downtime_type', 'downtime_reduce_in_time', 'downtime_schedule_line_ids', 'holiday_id.date_from',
                 'holiday_id.date_to')
    def _compute_possible_to_calculate_in_days(self):
        for rec in self:
            if rec.downtime_type != 'full' or not rec.employee_schedule_is_regular:
                rec.possible_to_calculate_in_days = False
            else:
                downtime_from_dt = datetime.strptime(rec.date_from_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
                downtime_to_dt = datetime.strptime(rec.date_to_date_format, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = (downtime_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = (downtime_to_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                partial_bonuses_exist_in_period = self.search_count([
                    ('date_from', '<=', date_to),
                    ('date_to', '>=', date_from),
                    ('employee_id', '=', rec.employee_id.id),
                    ('downtime_type', '=', 'partial')
                ])
                rec.possible_to_calculate_in_days = not partial_bonuses_exist_in_period

    @api.one
    @api.depends('holiday_id.date_from', 'holiday_id.date_to')
    def _compute_employee_schedule_is_regular(self):
        appointment = self.contract_id.with_context(date=self.date_from_date_format).appointment_id
        self.employee_schedule_is_regular = appointment and appointment.schedule_template_id.template_type in \
                                            ['fixed', 'suskaidytos']

    @api.one
    @api.depends('holiday_id.date_from', 'holiday_id.date_to')
    def _compute_downtime_duration(self):
        self.downtime_duration = (datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT) -
                                  datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)).days + 1

    @api.one
    @api.depends('holiday_id.state')
    def _compute_state(self):
        if self.holiday_id.state == 'validate':
            self.state = 'confirm'
        else:
            self.state = 'draft'

    @api.one
    @api.depends('downtime_reduce_in_time', 'downtime_schedule_line_ids', 'holiday_id.date_from', 'holiday_id.date_to')
    def _compute_downtime_weekly_time(self):
        if self.downtime_reduce_in_time:
            self.downtime_weekly_days = 0
            self.downtime_weekly_hours = self.downtime_reduce_in_time
        else:
            appointment = self.contract_id.with_context(date=self.date_from_date_format).appointment_id
            if not appointment or appointment.schedule_template_id.template_type not in ['fixed', 'suskaidytos']:
                self.downtime_weekly_hours = self.downtime_weekly_days = 0
            else:
                employee_attendance_ids = appointment.schedule_template_id.fixed_attendance_ids
                downtime_attendance_ids = self.downtime_schedule_line_ids

                len_previous_days = len(set(employee_attendance_ids.mapped('dayofweek')))
                len_new_days = len(set(downtime_attendance_ids.mapped('weekday')))

                previous_time_total = sum(employee_attendance_ids.mapped('time_total'))
                new_time_total = sum(downtime_attendance_ids.mapped('time_total'))

                days_should_have_shortened = min(2, len_previous_days)

                hours_shortened = max(previous_time_total - new_time_total, 0.0)
                days_shortened = max(len_previous_days - len_new_days, 0)
                week_day_length_reduced = days_shortened >= days_should_have_shortened

                force_calculate_in_hours = False
                for weekday in downtime_attendance_ids.mapped('weekday'):
                    regular_attendances_for_day = employee_attendance_ids.filtered(lambda d: d.dayofweek == weekday)
                    downtime_attendance_for_day = downtime_attendance_ids.filtered(lambda d: d.weekday == weekday)
                    regular_work_time = sum(regular_attendances_for_day.mapped('time_total'))
                    downtime_work_time = sum(downtime_attendance_for_day.mapped('time_total'))
                    if tools.float_compare(regular_work_time, downtime_work_time, precision_digits=2) != 0:
                        force_calculate_in_hours = True
                        break

                if week_day_length_reduced and not force_calculate_in_hours:
                    self.downtime_weekly_days = days_shortened
                else:
                    self.downtime_weekly_days = 0

                self.downtime_weekly_hours = hours_shortened

    @api.multi
    @api.constrains('come_to_work_schedule_line_ids', 'downtime_type', 'downtime_subtype')
    def _check_come_to_work_schedule(self):
        for rec in self:
            if rec.downtime_type == 'full' and rec.downtime_subtype == 'ordinary' \
                    and rec.downtime_duration in [1, 2, 3]:
                downtime_start_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                downtime_end_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                appointments = self.env['hr.contract.appointment'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date_start', '<=', rec.date_to_date_format),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', rec.date_from_date_format)
                ])
                found = 0
                dates = []
                while (downtime_start_dt <= downtime_end_dt) and found < rec.downtime_duration:
                    date = downtime_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    appointment = appointments.filtered(lambda a: a.date_start <= date and (
                            not a.date_end or a.date_end >= date))
                    if appointment and appointment.schedule_template_id.is_work_day(date):
                        found += 1
                        dates.append(date)
                    downtime_start_dt += relativedelta(days=1)
                if not all(date in dates for date in rec.come_to_work_schedule_line_ids.mapped('date')):
                    raise exceptions.ValidationError(
                        _('Darbuotojo galima prašyti atvykti į darbą tik šiomis dienomis: {}').format(dates))

    @api.multi
    def downtime_duration_based_on_schedule(self, date_from=None, date_to=None):
        """
        Calculates the actual downtime time based on the employee schedule for period. Can not be used for any other
        schedule than 'fixed' or 'suskaidytos'
        No illnesses or other absences can exist in the downtime period so it's not too complicated to calculate.
        :rtype: (float) duration of the downtime in days or hours depending if downtime can be calculated in days or
        0.0 if not possible to calculate
        """
        self.ensure_one()

        if not date_from:
            date_from = self.date_from_date_format
        if not date_to:
            date_to = self.date_to_date_format

        if date_from > self.date_to_date_format:
            raise exceptions.UserError(_('Negalima nustatyti prastovos dienų skaičiaus periodui, nes reikalaujamo '
                                         'periodo pradžia {} yra vėliau už prastovos pabaigą '
                                         '({})').format(date_from, self.date_to_date_format))
        if date_to < self.date_from_date_format:
            raise exceptions.UserError(_('Negalima nustatyti prastovos dienų skaičiaus periodui, nes reikalaujamo '
                                         'periodo pabaiga {} yra anksčiau už prastovos pradžią '
                                         '({})').format(date_to, self.date_from_date_format))

        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

        appointments = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_start', '<=', self.date_to_date_format),
            '|',
            ('date_end', '>=', self.date_from_date_format),
            ('date_end', '=', False)
        ])
        schedule_types = appointments.mapped('schedule_template_id.template_type')
        if any(schedule_type not in ['fixed', 'suskaidytos'] for schedule_type in schedule_types):
            return 0.0

        calculate_in_days = self.possible_to_calculate_in_days
        duration = 0.0
        while date_from_dt <= date_to_dt:
            date = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            appointment = appointments.filtered(lambda a: a.date_start <= date and (not a.date_end or
                                                                                    a.date_end >= date))
            if not appointment or not appointment.schedule_template_id.is_work_day(date):
                date_from_dt += relativedelta(days=1)
                continue

            weekday = date_from_dt.weekday()
            downtime_schedule_for_date = self.downtime_schedule_line_ids.filtered(lambda s: int(s.weekday) == weekday)

            if calculate_in_days and not downtime_schedule_for_date:
                duration += 1
            else:
                date_regular_hours = self.env['hr.employee'].employee_work_norm(
                    calc_date_from=date,
                    calc_date_to=date,
                    contract=appointment.contract_id,
                    appointment=appointment)['hours']
                date_downtime_hours = sum(downtime_schedule_for_date.mapped('time_total'))
                duration += max(date_regular_hours - date_downtime_hours, 0.0)
            date_from_dt += relativedelta(days=1)

        return duration

HrEmployeeDowntime()


class HrEmployeeDowntimeScheduleLine(models.Model):
    _name = 'hr.employee.downtime.schedule.line'

    hr_employee_downtime_id = fields.Many2one('hr.employee.downtime', string='Downtime record', required=True, ondelete='cascade')
    date = fields.Date(string='Date', index=True, inverse='_set_weekday_of_date')
    weekday = fields.Selection([
        ('0', 'Pirmadienis'),
        ('1', 'Antradienis'),
        ('2', 'Trečiadienis'),
        ('3', 'Ketvirtadienis'),
        ('4', 'Penktadienis'),
        ('5', 'Šeštadienis'),
        ('6', 'Sekmadienis')
    ], string='Savaitės Diena')
    time_from = fields.Float(string='Darbo laikas nuo', required=True, index=True)
    time_to = fields.Float(string='Darbo laikas iki', required=True)
    time_total = fields.Float(string='Trukmė', compute='_compute_time_total')

    @api.one
    @api.depends('date')
    def _compute_weekday(self):
        if self.date:
            date_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.weekday = str(date_dt.weekday())

    @api.one
    @api.depends('time_from', 'time_to')
    def _compute_time_total(self):
        if self.time_from and self.time_to:
            self.time_total = self.time_to - self.time_from
        else:
            self.time_total = 0.0

    @api.multi
    @api.constrains('time_from', 'time_to')
    def _check_hours_valid(self):
        for rec in self:
            if rec.time_to and rec.time_from and rec.time_to <= rec.time_from:
                raise exceptions.ValidationError(_('Dirbama iki turi būti daugiau nei dirbama nuo'))

    @api.multi
    @api.constrains('time_from', 'time_to')
    def _check_hours_fit_day(self):
        for rec in self:
            if not 0 <= rec.time_from <= 24 or not 0 <= rec.time_to <= 24:
                raise exceptions.ValidationError(_('Grafiko laikas turi būti nuo 00:00 iki 24:00'))

    @api.one
    def _set_weekday_of_date(self):
        if self.date:
            self.weekday = str(datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday())


HrEmployeeDowntimeScheduleLine()
