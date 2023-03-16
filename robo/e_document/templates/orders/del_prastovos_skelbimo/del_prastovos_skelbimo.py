# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, fields, exceptions, _, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class EDocument(models.Model):
    _inherit = 'e.document'

    downtime_type = fields.Selection(
        [('full', _('Full time')), ('partial', _('Partial'))],
        string='Downtime type',
        default='full',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )

    downtime_subtype = fields.Selection(
        [('ordinary', _('Ordinary')), ('due_to_special_cases', _('Due to special cases'))],
        string='Downtime subtype',
        default='due_to_special_cases',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )  # TODO Change default to 'ordinary' later.

    downtime_reason = fields.Text(
        string='Downtime reason',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )

    downtime_related_state_declared_emergency = fields.Many2one(
        'state.declared.emergency',
        string='State declared emergency or quarantine',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True,
        inverse='set_final_document'
    )

    downtime_related_state_declared_emergency_ref_text = fields.Text(
        related='downtime_related_state_declared_emergency.reference_text'
    )

    downtime_duration = fields.Integer(
        compute='_compute_downtime_duration'
    )

    # Used for full time downtime that is not due to extreme causes or quarantine
    downtime_employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )

    prastova_employee_list = fields.Html(
        compute='_compute_prastova_employee_list'
    )

    downtime_come_to_work_times = fields.One2many(
        'date.work.time.line',
        'e_document',
        string='Laikas, kuomet darbuotojas privalo būti darbe',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )

    downtime_time_adjustable = fields.Boolean(
        compute='_compute_downtime_time_adjustable'
    )

    downtime_fixed_attendance_ids = fields.One2many(
        'e.document.fix.attendance.line',
        'e_document',
        string='Schedule',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True
    )

    downtime_reduce_in_time = fields.Float(
        string='Reduce work time by'
    )

    downtime_pay_selection = fields.Selection(
        [
            ('mma', _('Mokėti MMA, paskaičiuotą pagal darbo laiko normą')),
            ('salary', _('Mokėti darbuotojo darbo užmokesčio dalį neviršijančią 1,5 minimalaus mėnesinio atlyginimo')),
            ('custom', _('Įvesti')),
        ],
        inverse='set_final_document',
        string='Apmokėjimas už prastovą',
        default='mma',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True)

    employee_schedule_is_regular = fields.Boolean(
        compute='_compute_employee_schedule_is_regular'
    )

    employee_downtime_schedule_table = fields.Html(
        compute='_compute_employee_downtime_schedule_table'
    )

    prastova_employee_ids = fields.Many2many(
        'hr.employee',
        string='Darbuotojai',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True,
        relation='rel_e_document_prastova_employee_ids',
        required=True
    )

    downtime_appointment_id = fields.Many2one(
        'hr.contract.appointment',
        compute='_compute_downtime_appointment_id'
    )

    downtime_schedule_reduction = fields.Text(compute='_compute_downtime_schedule_reduction')
    inform_of_possible_higher_compensation = fields.Boolean(compute='_compute_inform_of_possible_higher_compensation')

    @api.multi
    @api.depends('downtime_pay_selection', 'date_to')
    def _compute_inform_of_possible_higher_compensation(self):
        for rec in self:
            if rec.date_to and rec.date_to >= '2021-07-01' and rec.downtime_pay_selection != 'salary':
                rec.inform_of_possible_higher_compensation = True

    @api.one
    @api.depends('employee_id2', 'date_from', 'date_to', 'downtime_fixed_attendance_ids')
    def _compute_downtime_schedule_reduction(self):
        if not self.employee_schedule_is_regular or not self.is_prastova_doc():
            self.downtime_schedule_reduction = ''
        else:
            employee_attendance_ids = self.downtime_appointment_id.schedule_template_id.fixed_attendance_ids
            downtime_attendance_ids = list(set((rec.dayofweek, rec.hour_from, rec.hour_to) for rec in self.downtime_fixed_attendance_ids))

            len_previous_days = len(set(employee_attendance_ids.mapped('dayofweek')))
            downtime_weekdays = set(rec[0] for rec in downtime_attendance_ids)
            len_new_days = len(downtime_weekdays)

            previous_time_total = sum(employee_attendance_ids.mapped('time_total'))
            new_time_total = sum(rec[2] - rec[1] for rec in downtime_attendance_ids)

            hours_should_have_shortened = len_previous_days * 3  # 3 Hours must be shortened every day
            days_should_have_shortened = min(2, len_previous_days)

            hours_shortened = previous_time_total - new_time_total
            shortened_hours = tools.float_compare(hours_shortened, hours_should_have_shortened, precision_digits=2) >= 0

            days_shortened = (len_previous_days - len_new_days)
            week_day_length_reduced = days_shortened >= days_should_have_shortened

            additionally_shortened = 0.0
            if days_shortened:
                previous_days = employee_attendance_ids.filtered(lambda a: a.dayofweek not in downtime_weekdays)
                duration_of_those_days = sum(previous_days.mapped('time_total'))
                additionally_shortened = hours_shortened - duration_of_those_days

            base_str = 'Prastovos laikotarpiu darbuotojo darbo grafikas trumpinamas'

            if week_day_length_reduced:
                schedule_reduction = base_str + ' {} dienomis'.format(days_shortened)
                if not tools.float_is_zero(additionally_shortened, precision_digits=2):
                    hours, minutes = divmod(additionally_shortened * 60, 60)
                    hours = round(hours)
                    schedule_reduction += ' ir {} '.format(int(hours))
                    if tools.float_compare(int(round(minutes)), 60, precision_digits=3) == 0:
                        minutes = 0
                        hours += 1
                    if int(hours) % 10 == 0:
                        schedule_reduction += 'valandų'
                    elif 10 < int(hours) % 100 < 20:
                        schedule_reduction += 'valandų'
                    elif int(hours) % 10 == 1:
                        schedule_reduction += 'valanda'
                    else:
                        schedule_reduction += 'valandomis'
                    if not tools.float_is_zero(minutes, precision_digits=2):
                        minutes = round(minutes)
                        schedule_reduction += ' {} '.format(int(round(minutes)))
                        if int(minutes) % 10 == 0:
                            schedule_reduction += 'minučių'
                        elif 10 < int(minutes) % 100 < 20:
                            schedule_reduction += 'minučių'
                        elif int(minutes) % 10 == 1:
                            schedule_reduction += 'minute'
                        else:
                            schedule_reduction += 'minutėmis'
                schedule_reduction += ' per savaitę.'
                self.downtime_schedule_reduction = schedule_reduction
            elif shortened_hours:
                hour_naming = 'valandomis'
                if int(hours_shortened) % 10 == 0:
                    hour_naming = 'valandų'
                elif 10 < int(hours_shortened) % 100 < 20:
                    hour_naming = 'valandų'
                elif int(hours_shortened) % 10 == 1:
                    hour_naming = 'valanda'
                else:
                    pass

                self.downtime_schedule_reduction = base_str + ' {} {} per savaitę'.format(
                    self.format_float_to_hours(hours_shortened),
                    hour_naming
                )
            else:
                self.downtime_schedule_reduction = ''

    @api.one
    @api.depends('employee_id2', 'date_from')
    def _compute_downtime_appointment_id(self):
        if not self.employee_id2 or not self.date_from or not self.is_prastova_doc():
            self.downtime_appointment_id = False
        else:
            self.downtime_appointment_id = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_start', '<=', self.date_from),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from),
            ], order='date_start asc', limit=1)

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        docs = self.filtered(lambda d: d.is_prastova_doc())
        for doc in docs:
            if doc.date_to and doc.date_from > doc.date_to:
                raise exceptions.UserError(_('Prastova turi prasidėti prieš prastovos pabaigą'))

            downtime_start_dt = datetime.strptime(doc.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            downtime_end_dt = datetime.strptime(doc.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

            # Salary to be paid for downtime in order to receive compensation is only allowed from January 1st 2021
            if doc.downtime_subtype != 'ordinary' and doc.downtime_pay_selection == 'salary':
                if self.date_from < '2021-01-01':
                    raise exceptions.UserError(_('Rinktis mokėti darbuotojo darbo užmokesčio dalį neviršijančią 1,5 '
                                                 'minimalaus mėnesinio atlyginimo galima tik nuo 2021m. Sausio 1d.'))

            # ===================== Check that the employee has an active appointment at all times =====================
            downtime_period_appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', doc.employee_id2.id),
                ('date_start', '<=', doc.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', doc.date_from)
            ])

            dates_without_appointment = []
            check_date_dt = downtime_start_dt
            while check_date_dt <= downtime_end_dt:
                check_date = check_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                downtime_appointment_for_date = downtime_period_appointments.filtered(lambda a:
                                                                                      a.date_start <= check_date and
                                                                                      (not a.date_end or
                                                                                       a.date_end >= check_date))
                if not downtime_appointment_for_date:
                    dates_without_appointment.append(check_date)
                check_date_dt += relativedelta(days=1)

            if dates_without_appointment:
                raise exceptions.UserError(_('Darbuotojas ne visu prastovos laikotarpiu turi aktyvų darbo sutarties '
                                             'priedą. Patikrinkite darbuotojo darbo sutarties laikotarpį. Priedas '
                                             'nerastas šioms datoms: {}').format(',\n'.join(dates_without_appointment)))
            # ==========================================================================================================

            # ===================== Check that the entered downtime pay amount is no less than MMA =====================
            if doc.downtime_subtype != 'ordinary' and doc.downtime_pay_selection == 'custom':

                minimum_downtime_pay = 0.0

                new_schedule = doc.downtime_fixed_attendance_ids
                new_days_per_week = len(new_schedule.mapped('dayofweek'))

                national_holiday_dates = self.env['sistema.iseigines'].sudo().search([
                    ('date', '<=', self.date_to),
                    ('date', '>=', self.date_from)
                ]).mapped('date')

                date_periods = []
                check_date_dt = downtime_start_dt
                while check_date_dt <= downtime_end_dt:
                    date_periods.append((check_date_dt.year, check_date_dt.month))
                    check_date_dt += relativedelta(days=1)
                date_periods = set(date_periods)

                for (period_year, period_month) in date_periods:
                    period_start = datetime(year=period_year, month=period_month, day=1)
                    period_end = period_start + relativedelta(day=31)

                    period_downtime_start_dt = max(period_start, downtime_start_dt)
                    period_downtime_end_dt = min(period_end, downtime_end_dt)
                    month_start = period_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    month_end = period_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    period_downtime_start = period_downtime_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    period_downtime_end = period_downtime_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    period_duration = (period_downtime_end_dt - period_downtime_start_dt).days + 1

                    Contract = self.env['hr.contract'].with_context(date=period_downtime_start)
                    period_tax_rates = Contract.get_payroll_tax_rates(fields_to_get=['mma'])
                    minimum_wage = period_tax_rates['mma']

                    regular_month_work_data = self.env['hr.payroll'].standard_work_time_period_data(
                        month_start, month_end)

                    month_work_days = regular_month_work_data['days']
                    month_work_hours = regular_month_work_data['hours']
                    minimum_daily_wage = minimum_wage / float(month_work_days)  # P3:DivOK
                    minimum_hourly_wage = minimum_wage / float(month_work_hours)  # P3:DivOK

                    if doc.downtime_type != 'full' and not doc.employee_schedule_is_regular:
                        # P3:DivOK
                        downtime_duration = doc.downtime_reduce_in_time / 7.0 * period_duration  # 7 days in a week
                        minimum_downtime_pay += minimum_hourly_wage * downtime_duration
                        continue

                    period_appointments = downtime_period_appointments.filtered(
                        lambda a: a.date_start <= period_downtime_end and
                                  (not a.date_end or a.date_end >= period_downtime_start)
                    )

                    for period_appointment in period_appointments:

                        regular_month_work_data = self.env['hr.payroll'].standard_work_time_period_data(
                            month_start, month_end,
                            six_day_work_week=period_appointment.schedule_template_id.num_week_work_days == 6)

                        month_work_days = regular_month_work_data['days']
                        month_work_hours = regular_month_work_data['hours']
                        minimum_daily_wage = minimum_wage / float(month_work_days)  # P3:DivOK
                        minimum_hourly_wage = minimum_wage / float(month_work_hours)  # P3:DivOK

                        calculate_in_hours = not period_appointment.schedule_template_id.wage_calculated_in_days

                        calculation_start_date = max(period_downtime_start, period_appointment.date_start)
                        calculation_end_date = period_downtime_end
                        if period_appointment.date_end:
                            calculation_end_date = min(period_downtime_end, period_appointment.date_end)

                        if doc.downtime_type == 'full':
                            period_appointment_work_norm = self.env['hr.employee'].employee_work_norm(
                                calc_date_from=calculation_start_date,
                                calc_date_to=calculation_end_date,
                                contract=period_appointment.contract_id,
                                appointment=period_appointment
                            )
                            if calculate_in_hours:
                                downtime_duration = period_appointment_work_norm.get('hours')
                                # P3:DivOK
                                appointment_adjusted_downtime_pay = minimum_hourly_wage * \
                                                                    period_appointment.schedule_template_id.etatas / \
                                                                    period_appointment.schedule_template_id.work_norm
                            else:
                                downtime_duration = period_appointment_work_norm.get('days')
                                # P3:DivOK
                                appointment_adjusted_downtime_pay = minimum_daily_wage * \
                                                                    period_appointment.schedule_template_id.etatas / \
                                                                    period_appointment.schedule_template_id.work_norm
                            minimum_downtime_pay += appointment_adjusted_downtime_pay * downtime_duration
                            continue
                        else:
                            current_schedule = period_appointment.schedule_template_id.mapped('fixed_attendance_ids')

                            current_days_per_week = len(current_schedule.mapped('dayofweek'))

                            calculation_start_date_dt = datetime.strptime(
                                calculation_start_date,
                                tools.DEFAULT_SERVER_DATE_FORMAT
                            )
                            calculation_end_date_dt = datetime.strptime(
                                calculation_end_date,
                                tools.DEFAULT_SERVER_DATE_FORMAT
                            )

                            # Either has to be shortened 2 days or 3 hours per day
                            if current_days_per_week - new_days_per_week >= 2:
                                if period_appointment.schedule_template_id.work_week_type == 'six_day':
                                    weekends = [6]
                                elif period_appointment.schedule_template_id.work_week_type == 'based_on_template':
                                    week_days = range(0, 7)
                                    week_work_days = [int(day) for day in current_schedule.mapped('dayofweek')]
                                    weekends = list(set(week_days) - set(week_work_days))
                                else:
                                    weekends = [5, 6]

                                while calculation_start_date_dt <= calculation_end_date_dt:
                                    dayofweek = calculation_start_date_dt.weekday()
                                    calc_date = calculation_start_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                                    new_schedule_weekday_days = new_schedule.filtered(lambda l:
                                                                                      int(l.dayofweek) == dayofweek)
                                    if not new_schedule_weekday_days and dayofweek not in weekends and \
                                            calc_date not in national_holiday_dates:
                                        # P3:DivOK
                                        minimum_downtime_pay += minimum_daily_wage * \
                                                                period_appointment.schedule_template_id.etatas / \
                                                                period_appointment.schedule_template_id.work_norm
                                    calculation_start_date_dt += relativedelta(days=1)
                            else:
                                while calculation_start_date_dt <= calculation_end_date_dt:
                                    calc_date = calculation_start_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                                    if calc_date not in national_holiday_dates:
                                        dayofweek = calculation_start_date_dt.weekday()
                                        current_time_total = sum(current_schedule.filtered(
                                            lambda l: int(l.dayofweek) == dayofweek).mapped('time_total'))
                                        new_time_total = sum(new_schedule.filtered(
                                            lambda l: int(l.dayofweek) == dayofweek).mapped('time_total'))
                                        downtime_duration = max(current_time_total - new_time_total, 0.0)
                                        minimum_downtime_pay += downtime_duration * minimum_hourly_wage
                                    calculation_start_date_dt += relativedelta(days=1)

                minimum_downtime_pay = tools.float_round(minimum_downtime_pay, precision_digits=2)

                if tools.float_compare(doc.float_1, minimum_downtime_pay, precision_digits=2) < 0:
                    raise exceptions.UserError(_('Užmokestis už prastovą negali būti mažesnis nei pritaikytas MMA '
                                                 '({})').format(minimum_downtime_pay))
            # ==========================================================================================================

            # ===================================== Check come to work constraints =====================================
            if doc.downtime_type == 'full' and doc.downtime_subtype == 'ordinary':
                come_to_work_days = doc.downtime_come_to_work_times
                if len(come_to_work_days) > 3:
                    raise exceptions.UserError(_('Negalima nustatyti, kad darbuotojas atvyks į darbą vėliau, nei per '
                                                 'pirmas tris prastovos dienas'))

                date_check_dt = downtime_start_dt
                date_check_end = downtime_end_dt
                first_work_days = []
                while date_check_dt <= date_check_end:
                    date_check = date_check_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_app = downtime_period_appointments.filtered(lambda a: a.date_start <= date_check and
                                                                               (not a.date_end or a.date_end >= date_check))
                    if date_app and date_app.schedule_template_id.is_work_day(date_check):
                        first_work_days.append(date_check)
                    date_check_dt += relativedelta(days=1)

                come_to_work_day_dates = come_to_work_days.mapped('date')
                if any(date not in first_work_days for date in come_to_work_day_dates):
                    raise exceptions.UserError(_('Neteisingai nustatytos datos, kuomet darbuotojo reikalaujama būti '
                                                 'darbe'))

                if doc.downtime_duration == 1:
                    appointment_schedule_template = doc.downtime_appointment_id.schedule_template_id
                    max_work_time_each_day = (appointment_schedule_template.get_regular_hours(doc.date_from),)
                elif doc.downtime_duration <= 3:
                    # If downtime lasts no more than 4 days - max employees can come to work for is one hour.
                    max_work_time_each_day = (1, 1, 1)
                else:
                    # If downtime lasts more than 3 days - employees can not be required to come to work.
                    max_work_time_each_day = (0, 0, 0)

                days_to_check = min(3, doc.downtime_duration)

                for i in range(days_to_check):
                    max_work_time_for_day = max_work_time_each_day[i]
                    come_to_work_day = False
                    if i < len(first_work_days):
                        come_to_work_day = come_to_work_days.filtered(lambda d: d.date == first_work_days[i])
                    if not come_to_work_day:
                        continue
                    day_work_time = come_to_work_day.time_total
                    if tools.float_compare(day_work_time, max_work_time_for_day, precision_digits=2) > 0:
                        raise exceptions.UserError(_('Darbuotojas {0} {1}-ąją prastovos dieną į darbovietę gali atvykti '
                                                     'ne ilgesniam nei {2} valandos laikotarpiui, tačiau nustatyta, kad'
                                                     ' darbuotojas į darbovietę atvyks {3} laiko tarpui.').format(
                            doc.employee_id2.name,
                            i + 1,
                            max_work_time_for_day,
                            day_work_time
                        ))
            # ==========================================================================================================

            # =============================== Check correct amount of time has been shortened ==========================
            if doc.downtime_type != 'full':
                downtime_start_day_of_week = downtime_start_dt.weekday()
                week_start_dt = downtime_start_dt - relativedelta(days=downtime_start_day_of_week)
                week_end_dt = downtime_start_dt + relativedelta(days=7 - downtime_start_day_of_week - 1)
                week_start = week_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                week_end = week_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                schedule_template = doc.downtime_appointment_id.schedule_template_id
                weekly_hours = schedule_template.num_week_work_days * schedule_template.avg_hours_per_day

                if not doc.employee_schedule_is_regular:
                    employee_weekly_work_norm = self.env['hr.employee'].employee_work_norm(
                        calc_date_from=week_start,
                        calc_date_to=week_end,
                        contract=doc.downtime_appointment_id.contract_id,
                        appointment=doc.downtime_appointment_id)
                    max_that_could_be_reduced = weekly_hours
                    # 3 Hours must be shortened every day
                    min_that_had_to_be_reduced = min(employee_weekly_work_norm['days'] * 3, max_that_could_be_reduced)
                    if not doc.downtime_reduce_in_time or \
                            tools.float_compare(
                                max_that_could_be_reduced,
                                doc.downtime_reduce_in_time,
                                precision_digits=2
                            ) < 0 or \
                            tools.float_compare(
                                min_that_had_to_be_reduced,
                                doc.downtime_reduce_in_time,
                                precision_digits=2) > 0:
                        raise exceptions.UserError(_('Darbuotojui {0} darbo laikas privalo būti sutrumpintas tarp {1} '
                                                     'ir {2} valandų. Dabar nustatyta, kad darbuotojui darbo laikas '
                                                     'sutrumpinamas {3}h.').format(
                            doc.employee_id2.name,
                            min_that_had_to_be_reduced,
                            max_that_could_be_reduced,
                            doc.downtime_reduce_in_time
                        ))
                else:
                    employee_attendance_ids = doc.downtime_appointment_id.schedule_template_id.fixed_attendance_ids
                    downtime_attendance_ids = doc.downtime_fixed_attendance_ids

                    len_previous_days = len(set(employee_attendance_ids.mapped('dayofweek')))
                    len_new_days = len(set(downtime_attendance_ids.mapped('dayofweek')))

                    previous_time_total = sum(employee_attendance_ids.mapped('time_total'))
                    new_time_total = sum(downtime_attendance_ids.mapped('time_total'))

                    if tools.float_compare(new_time_total, previous_time_total, precision_digits=2) > 0:
                        raise exceptions.UserError(_('Prastovos metu darbuotojo {0} darbo laikas negali '
                                                     'pailgėti!').format(doc.employee_id2.name))

                    hours_should_have_shortened = len_previous_days * 3  # 3 Hours must be shortened every day
                    days_should_have_shortened = min(2, len_previous_days)

                    shortened_hours = tools.float_compare((previous_time_total - new_time_total),
                                                          hours_should_have_shortened, precision_digits=2) >= 0
                    shortened_days = (len_previous_days - len_new_days) >= days_should_have_shortened

                    if not shortened_days and not shortened_hours:
                        raise exceptions.UserError(_('Privalote sutrumpinti darbuotojo grafiką arba 2 darbo dienomis '
                                                     'per savaitę arba 3 valandomis kiekvieną darbo dieną'))
            # ==========================================================================================================

            # ===================================== CHECK DOWNTIME ALREADY EXISTS ======================================
            existing_downtime = self.env['hr.holidays'].search([
                ('date_from', '=', self.calc_date_from(doc.date_from)),
                ('date_to', '=', self.calc_date_to(doc.date_to)),
                ('employee_id', '=', doc.employee_id2.id),
                ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PN').id),
                ('type', '=', 'remove'),
            ])

            if existing_downtime:
                if existing_downtime.state not in ['draft', 'cancel', 'refuse']:  # We'll try to unlink later
                    raise exceptions.UserError(_('Nurodytam periodui šiam darbuotojui jau egzistuoja prastova'))
            # ==========================================================================================================

        return res

    @api.onchange('employee_id2', 'date_from')
    def _onchange_set_employee_schedule(self):
        if self.is_prastova_doc() and self.downtime_type != 'full' and self.downtime_appointment_id:
            ids = [
                (0, 0, {
                    'hour_from': fixed_attendance_id.hour_from,
                    'hour_to': fixed_attendance_id.hour_to,
                    'dayofweek': fixed_attendance_id.dayofweek
                }) for fixed_attendance_id in self.downtime_appointment_id.schedule_template_id.fixed_attendance_ids
            ]
            self.write({'downtime_fixed_attendance_ids': [(5,)] + ids})

    @api.onchange('employee_id2', 'date_from', 'date_to', 'template_id', 'downtime_type')
    def _onchange_set_come_to_work_days(self):
        if self.downtime_duration in [1, 2, 3] and self.date_from and self.date_to:
            downtime_start_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            downtime_end_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ])
            found = 0
            max_to_add = False
            if self.downtime_duration > 1:
                max_to_add = 1.0
            ids = []
            while (downtime_start_dt <= downtime_end_dt) and found < self.downtime_duration:
                date = downtime_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                appointments = appointments.filtered(lambda a: a.date_start <= date and (not a.date_end or a.date_end >= date))
                for appointment in appointments:
                    if appointment.schedule_template_id.is_work_day(date):
                        found += 1

                        date_hours = appointment.schedule_template_id.get_regular_hours(date)
                        if max_to_add:
                            date_hours = min(date_hours, max_to_add)

                        ids.append((0, 0, {
                            'hour_from': 8.0,
                            'hour_to': 8.0 + date_hours,
                            'date': date
                        }))  # TODO room for improvement
                        break  # Skip all other appointments.
                downtime_start_dt += relativedelta(days=1)

            self.write({'downtime_come_to_work_times': [(5,)] + ids})

    @api.one
    @api.depends('downtime_fixed_attendance_ids')
    def _compute_employee_downtime_schedule_table(self):
        schedule_rows = ''
        fixed_attendance_ids = self.downtime_fixed_attendance_ids.filtered(lambda l: l.id)
        if not fixed_attendance_ids:
            fixed_attendance_ids = self.downtime_fixed_attendance_ids
        weekday_naming = dict(fixed_attendance_ids._fields.get('dayofweek', False)._description_selection(self.env))
        for fixed_attendance_id in fixed_attendance_ids.sorted(key=lambda d: d.dayofweek):
            schedule_rows += '''<tr>
                    <td style="border: 1px solid black; padding: 2px;">{0}</td>
                    <td style="border: 1px solid black; padding: 2px;">{1}</td>
                    <td style="border: 1px solid black; padding: 2px;">{2}</td>
                </tr>'''.format(
                weekday_naming.get(fixed_attendance_id.dayofweek, ''),
                self.format_float_to_hours(fixed_attendance_id.hour_from),
                self.format_float_to_hours(fixed_attendance_id.hour_to)
            )

        self.employee_downtime_schedule_table = _('''<table style="border-collapse: collapse; margin-left: 20px;">
                    <tr>
                        <th style="border: 1px solid black; padding: 2px;">Savaitės diena</th>
                        <th style="border: 1px solid black; padding: 2px;">Darbo pradžia</th>
                        <th style="border: 1px solid black; padding: 2px;">Darbo pabaiga</th>
                    </tr>
                    {}
                    </table>''').format(schedule_rows)

    @api.one
    @api.depends('template_id', 'downtime_type')
    def _compute_downtime_time_adjustable(self):
        self.downtime_time_adjustable = self.is_prastova_doc() and self.downtime_type == 'partial'

    @api.one
    @api.depends('employee_id2', 'date_from')
    def _compute_employee_schedule_is_regular(self):
        if self.is_prastova_doc() and self.downtime_appointment_id:
            self.employee_schedule_is_regular = self.downtime_appointment_id.schedule_template_id.template_type in \
                                                ['fixed', 'suskaidytos']
        else:
            self.employee_schedule_is_regular = False

    @api.multi
    @api.constrains('date_from', 'date_to', 'template_id', 'downtime_subtype')
    def _check_special_downtime_subtype_duration(self):
        for rec in self:
            if rec.is_prastova_doc() and rec.downtime_subtype == 'due_to_special_cases':
                if rec.date_to and rec.date_to > rec.downtime_related_state_declared_emergency.date_end[:10]:
                    raise exceptions.UserError(_('Prastova turi baigtis prieš paskelbtos ekstremalios situacijos ar '
                                                 'karantino pabaigą ({})').format(
                        rec.downtime_related_state_declared_emergency.date_end[:10]
                    ))
                if rec.date_from and rec.date_from < rec.downtime_related_state_declared_emergency.date_start[:10]:
                    raise exceptions.UserError(_('Prastova turi prasidėti po paskelbtos ekstremalios situacijos ar '
                                                 'karantino pradžios datos ({})').format(
                        rec.downtime_related_state_declared_emergency.date_start[:10]
                    ))

    # @api.one
    # @api.constrains('date_from', 'date_to', 'template_id', 'downtime_type')
    # def _check_partial_downtime_duration(self):
    #     if self.is_prastova_doc() and self.date_from and self.date_to:
    #         if self.downtime_type == 'partial' and self.downtime_duration < 5:
    #             # Otherwise no need for partial/complicates stuff
    #             raise exceptions.UserError(_('Dalinė prastova turi trukti bent 5 dienas. Rinkitės viso darbo laiko '
    #                                          'prastovos įsakymą'))

    @api.one
    @api.depends('date_from', 'date_to', 'template_id')
    def _compute_downtime_duration(self):
        if not self.is_prastova_doc() or not self.date_from or not self.date_to:
            self.downtime_duration = 0
        else:
            self.downtime_duration = (datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) -
                                      datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)).days + 1

    @api.one
    @api.depends('downtime_employee_ids')
    def _compute_prastova_employee_list(self):
        employee_rows = ''
        for employee in self.downtime_employee_ids:
            employee_rows += '<tr><td style="border: 1px solid black; padding: 2px;">{0}</td></tr>'.format(
                employee.display_name
            )

        self.prastova_employee_list = '''<table style="border-collapse: collapse; margin-left: 20px;">
            <tr>
                <th style="border: 1px solid black; padding: 2px;">Vardas Pavardė</th>
            </tr>
            {}
        </table>'''.format(employee_rows)

    @api.multi
    def is_prastova_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.isakymas_del_prastovos_skelbimo_template', raise_if_not_found=False)
        is_doc = doc_to_check and self.sudo().template_id.id == doc_to_check.id
        if not is_doc:
            try:
                is_doc = doc_to_check and self.template_id.id == doc_to_check.id
            except:
                pass
        return is_doc

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        # Find the original document
        original_document = self.sudo().cancel_id

        if original_document and original_document.is_prastova_doc():
            employee_holiday = False
            if original_document.record_id and original_document.record_model == 'hr.holidays':
                employee_holiday = self.env['hr.holidays'].browse(original_document.record_id).exists()
            if not employee_holiday:
                holiday_records = self.env['hr.holidays'].search([
                    ('employee_id', '=', original_document.employee_id2.id),
                    '|',
                    ('numeris', '=', original_document.document_number),
                    '&',
                    ('date_from', '=', self.calc_date_from(original_document.date_from)),
                    ('date_to', '=', self.calc_date_to(original_document.date_to)),
                ])
                for holiday in holiday_records:
                    record = self.env['e.document'].search_count([
                        ('record_id', '=', holiday.id),
                        ('record_model', '=', 'hr.holidays'),
                    ])
                    if not record:
                        employee_holiday = holiday
                        break

            if employee_holiday:
                if employee_holiday.state != 'refuse':
                    employee_holiday.action_refuse()
            else:
                raise exceptions.ValidationError(_('Nerastas susijęs neatvykimas'))
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def isakymas_del_prastovos_skelbimo_workflow(self):
        self.ensure_one()

        existing_downtime = self.env['hr.holidays'].search([
            ('date_from', '=', self.calc_date_from(self.date_from)),
            ('date_to', '=', self.calc_date_to(self.date_to)),
            ('employee_id', '=', self.employee_id2.id),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PN').id),
            ('type', '=', 'remove'),
        ])

        if existing_downtime:
            if existing_downtime.state in ['cancel', 'refuse']:
                existing_downtime.action_draft()
            if existing_downtime.state == 'draft':
                existing_downtime.sudo().unlink()
            else:
                raise exceptions.UserError(_('Nurodytam periodui šiam darbuotojui jau egzistuoja prastova'))

        other_holidays = self.env['hr.holidays'].search([
            ('date_from', '<=', self.calc_date_to(self.date_to)),
            ('date_to', '>=', self.calc_date_from(self.date_from)),
            ('employee_id', '=', self.employee_id2.id),
            ('type', '=', 'remove'),
            ('state', '=', 'validate'),
            ('id', '!=', existing_downtime.id)
        ])

        if other_holidays:
            raise exceptions.UserError(_('Jūsų pasirinktame periode egzistuoja kiti neatvykimų įrašai, todėl šiam '
                                         'periodui prastova negali būti skelbiama.'))

        holiday = self.env['hr.holidays'].create({
            'name': 'Prastova',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_PN').id,
            'date_from': self.calc_date_from(self.date_from),
            'date_to': self.calc_date_to(self.date_to),
            'type': 'remove',
            'numeris': self.document_number,
        })

        schedule_line_ids = [
            (0, 0, {
                'time_from': fixed_attendance_id.hour_from,
                'time_to': fixed_attendance_id.hour_to,
                'weekday': fixed_attendance_id.dayofweek
            }) for fixed_attendance_id in self.downtime_fixed_attendance_ids
        ]

        come_to_work_line_ids = [
            (0, 0, {
                'date': fixed_attendance_id.date,
                'time_from': fixed_attendance_id.hour_from,
                'time_to': fixed_attendance_id.hour_to
            }) for fixed_attendance_id in self.downtime_come_to_work_times
        ]

        self.env['hr.employee.downtime'].sudo().create({
            'holiday_id': holiday.id,
            'downtime_type': self.downtime_type,
            'downtime_subtype': self.downtime_subtype,
            'reason': self.downtime_reason,
            'state_declared_emergency_id': self.downtime_related_state_declared_emergency.id,
            'downtime_schedule_line_ids': [(5,)] + schedule_line_ids,
            'come_to_work_schedule_line_ids': [(5,)] + come_to_work_line_ids,
            'pay_type': self.downtime_pay_selection,
            'pay_amount': self.float_1,
            'downtime_reduce_in_time': self.downtime_reduce_in_time
        })

        holiday.action_approve()
        self.inform_about_creation(holiday)

        self.write({
            'record_model': 'hr.holidays',
            'record_id': holiday.id,
        })

    @api.multi
    def sign(self, **kwargs):
        if not self._context.get('simulate'):
            for rec in self:
                if rec.is_prastova_doc() and rec.downtime_type == 'partial':
                    rec.write({'name': 'Įsakymas dėl dalinės prastovos skelbimo'})
        return super(EDocument, self).sign(**kwargs)


EDocument()
