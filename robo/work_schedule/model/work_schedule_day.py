# -*- coding: utf-8 -*-
import ast
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools import float_compare
from odoo.tools.translate import _
from work_schedule import SCHEDULE_STATES
from odoo.addons.l10n_lt_payroll.model.schedule_tools import find_time_to_set, merge_line_values
from six import iteritems


class WorkScheduleDay(models.Model):
    _name = 'work.schedule.day'

    _order = 'date'

    _sql_constraints = [('work_schedule_line_days_unique', 'unique(work_schedule_line_id, date)',
                         _('Vienoje skyriaus eilutėje negali egzistuoti keli įrašai su ta pačia data'))]

    name = fields.Char('Pavadinimas')

    work_schedule_line_id = fields.Many2one('work.schedule.line', _('Grafiko eilutė'), required=True,
                                            ondelete='cascade', inverse='_reset_schedule_line_constraints')
    work_schedule_id = fields.Many2one('work.schedule', related='work_schedule_line_id.work_schedule_id')
    line_ids = fields.One2many('work.schedule.day.line', 'day_id', _('Dienos eilutės'), readonly=True,
                               states={'draft': [('readonly', False)]}, inverse='_reset_schedule_line_constraints')

    date = fields.Date(string='Data', required=True, readonly=True, inverse='_reset_schedule_line_constraints')
    state = fields.Selection(SCHEDULE_STATES, related='work_schedule_line_id.state', default='draft',
                             inverse='_reset_schedule_line_constraints')

    business_trip = fields.Boolean(string='Komandiruotė', readonly=True, states={'draft': [('readonly', False)]},
                                   inverse='_reset_schedule_line_constraints')
    free_day = fields.Boolean(string='Poilsio diena', readonly=True, states={'draft': [('readonly', False)]},
                              inverse='_reset_schedule_line_constraints')

    schedule_holiday_id = fields.Many2one('work.schedule.holidays', string='Susijusios atostogos',
                                          compute='_compute_schedule_holiday_id')

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', related='work_schedule_line_id.employee_id')
    appointment_id = fields.Many2one('hr.contract.appointment', string='Sutarties priedas',
                                     compute='_compute_appointment_and_contract')
    contract_id = fields.Many2one('hr.contract', string='Darbo sutartis',
                                  compute='_compute_appointment_and_contract')
    department_id = fields.Many2one('hr.department', string='Padalinys', related='work_schedule_line_id.department_id')
    holiday_ids = fields.Many2many('hr.holidays', string='Holiday', compute='_compute_holiday_ids')
    holidays_for_the_entire_day = fields.Boolean('Is the related holiday for the entire day',
                                                 compute='_compute_holiday_ids')

    @api.multi
    def _reset_schedule_line_constraints(self):
        self.mapped('work_schedule_line_id').sudo().write({'constraint_check_data': ''})

    @api.multi
    @api.depends('date', 'employee_id')
    def _compute_holiday_ids(self):
        holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('date_from_date_format', '<=', max(self.mapped('date'))),
            ('date_to_date_format', '>=', min(self.mapped('date'))),
            ('holiday_status_id', '!=', self.env.ref('hr_holidays.holiday_status_K').id)
        ])
        for rec in self:
            related_holidays = holidays.filtered(
                lambda h: h.date_from_date_format <= rec.date <= h.date_to_date_format and
                          h.employee_id == rec.employee_id
            )
            related_work_schedule_codes = self.env['work.schedule.codes'].search([
                ('tabelio_zymejimas_id', 'in', related_holidays.mapped('holiday_status_id.tabelio_zymejimas_id').ids)
            ])
            rec.holidays_for_the_entire_day = any(rwsc.is_whole_day for rwsc in related_work_schedule_codes)
            rec.holiday_ids = related_holidays

    @api.multi
    def name_get(self):
        return [(rec.id, '%s (%s) (%s)' % (rec.employee_id.name, rec.department_id.name, rec.date)) for rec in self]

    @api.one
    def _compute_schedule_holiday_id(self):
        self.schedule_holiday_id = self.env['work.schedule.holidays'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '<=', self.date),
            ('date_to', '>=', self.date)
        ], limit=1)

    @api.multi
    def check_state_rules(self):
        states_allowed_to_be_modified = ['draft']
        if self.env.user.has_group('robo_basic.group_robo_premium_chief_accountant'):
            states_allowed_to_be_modified += ['validated', 'confirmed']
        if any(day.state not in states_allowed_to_be_modified for day in self):
            raise exceptions.ValidationError(
                _('Negalite keisti pasirinkto grafiko, nes yra įrašų, kurie jau patvirtinti'))

    @api.multi
    @api.constrains('line_ids')
    def _check_free_day_with_work_time(self):
        for rec in self:
            if not tools.float_is_zero(sum(rec.mapped('line_ids.worked_time_total')), precision_digits=2):
                rec.free_day = False

    @api.multi
    @api.constrains('free_day')
    def _check_free_day_with_work_time_and_unlink(self):
        for rec in self.filtered('free_day'):
            rec.line_ids.unlink()

    @api.multi
    @api.constrains('line_ids')
    def _check_and_remove_blank_lines(self):
        for rec in self:
            for line in rec.line_ids:
                if float_compare(line.time_to - line.time_from, 0.0, precision_digits=2) <= 0 \
                        and not line.work_schedule_code_id.is_whole_day:
                    line.unlink()

    @api.multi
    @api.constrains('line_ids')
    def _check_overlapping_times(self):
        for rec in self:
            all_date_days_for_employee = self.search([
                ('date', '=', rec.date),
                ('work_schedule_id', '=', rec.work_schedule_id.id),
                ('employee_id', '=', rec.employee_id.id)
            ])
            line_ids = all_date_days_for_employee.mapped('line_ids').sorted(key=lambda r: (r['time_from'], r['time_to']))
            hours_from = line_ids[1:].mapped('time_from')
            hours_to = line_ids[:-1].mapped('time_to')
            if any(h_from < h_to for h_from, h_to in zip(hours_from, hours_to)):
                raise exceptions.ValidationError(_(
                    'Darbuotojui %s negalima nustatyti šio darbo laiko, nes darbo laikas kertasi su jau nustatytu laiku.') % rec.employee_id.name)

    @api.multi
    @api.constrains('business_trip')
    def _check_business_trip_confirmed(self):
        for rec in self.filtered(lambda x: not x.business_trip):
            holidays_id = self.env.ref('hr_holidays.holiday_status_K').id
            holidays = self.env['hr.holidays'].sudo().search_count([
                ('date_from_date_format', '<=', rec.date),
                ('date_to_date_format', '>=', rec.date),
                ('employee_id', '=', rec.employee_id.id),
                ('state', '=', 'validate'),
                ('holiday_status_id', '=', holidays_id)
            ])
            if holidays:
                if not self._context.get('no_raise'):
                    raise exceptions.ValidationError(
                        _('Negalima pakeisti, jog diena nėra komandiruotė, nes tai jau patvirtinta'))
                else:
                    if not self._context.get('no_business_trip_reset'):
                        rec.business_trip = True

    @api.multi
    @api.depends('employee_id', 'date')
    def _compute_appointment_and_contract(self):
        dates = self.mapped('date')
        min_date, max_date = min(dates), max(dates)
        contracts = self.sudo().env['hr.contract'].search([
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('date_start', '<=', max_date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min_date)
        ])
        for rec in self:
            contract = contracts.filtered(
                lambda c: c.employee_id == rec.employee_id and
                          c.date_start <= rec.date and (not c.date_end or c.date_end >= rec.date)
            )
            appointment = contract.with_context(date=rec.date).appointment_id if contract else False
            rec.appointment_id = appointment.id if appointment else False
            rec.contract_id = contract.id if contract else False

    @api.multi
    @api.constrains('line_ids')
    def _check_write_access(self):
        if not self.env.user.is_schedule_manager():
            if not self.env.user.can_modify_schedule_departments(self.mapped('department_id.id')):
                raise exceptions.UserError(_('Neturite prieigos teisių modifikuoti grafiką'))

    @api.multi
    @api.constrains('line_ids')
    def _check_active_appointment(self):
        for rec in self:
            if not rec.appointment_id:
                raise exceptions.ValidationError(
                    _('Darbuotojo %s darbo laikas datai %s negali būti nustatytas.\n'
                      'Šis darbuotojas neturi aktyvių darbo sutarties priedų.') % (rec.employee_id.name, rec.date))

    @api.multi
    @api.constrains('business_trip')
    def _check_business_trip(self):
        for rec in self:
            other_department_days = self.env['work.schedule.day'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '=', rec.date),
                ('department_id', '!=', rec.department_id.id),
                ('work_schedule_id', '=', rec.work_schedule_id.id)
            ])
            if other_department_days and not self._context.get('do_not_fill_schedule'):
                if any(day.state != 'draft' for day in other_department_days):
                    if rec.business_trip != other_department_days[0].business_trip:
                        rec.business_trip = other_department_days[0].business_trip
                else:
                    for other_day in other_department_days:
                        if other_day.business_trip != rec.business_trip:
                            other_day.write({'business_trip': rec.business_trip})

    @api.multi
    @api.constrains('line_ids')
    def _ensure_no_duplicate_lines(self):
        for rec in self:
            unique_line_values = set([(l.time_from, l.time_to, l.work_schedule_code_id.id) for l in rec.line_ids])
            for unique_value in unique_line_values:
                unique_time_from = unique_value[0]
                unique_time_to = unique_value[1]
                unique_work_schedule_code_id = unique_value[2]
                lines_by_unique_value = rec.line_ids.filtered(
                    lambda r: r.time_from == unique_time_from and r.time_to == unique_time_to
                    and r.work_schedule_code_id.id == unique_work_schedule_code_id
                )
                if len(lines_by_unique_value) > 1:
                    self.env['work.schedule.day.line'].browse(lines_by_unique_value.mapped('id')[1:]).unlink()

    @api.multi
    @api.constrains('line_ids')
    def _check_work_hours_night(self):
        dn_zymejimas = self.env.ref('work_schedule.work_schedule_code_DN')
        overtime_nights_marking = self.env.ref('work_schedule.work_schedule_code_VDN')
        overtime_marking = self.env.ref('work_schedule.work_schedule_code_VD')
        overtime_on_holidays_marking = self.env.ref('work_schedule.work_schedule_code_VSS')
        snv_zymejimas = self.env.ref('work_schedule.work_schedule_code_SNV')
        public_holidays = self.env['sistema.iseigines'].search([('date', 'in', self.mapped('date'))]).mapped('date')
        WorkScheduleDayLine = self.env['work.schedule.day.line']

        def create_night_lines(env_obj, lines, morning=True):
            for line in lines:
                between_night_and_day = float_compare(line.time_to, night_time_end,
                                                      precision_digits=2) > 0 if morning else float_compare(
                    line.time_from, night_time_start, precision_digits=2) < 0
                is_overtime = line.work_schedule_code_id in [overtime_nights_marking, overtime_marking, overtime_on_holidays_marking]
                if line.date in public_holidays:
                    zymejimas_to_use = overtime_on_holidays_marking if is_overtime else snv_zymejimas
                else:
                    zymejimas_to_use = overtime_nights_marking if is_overtime else dn_zymejimas
                if between_night_and_day:
                    vals_1 = {
                        'work_schedule_code_id': zymejimas_to_use.id,
                        'time_from': line.time_from if morning else night_time_start,
                        'time_to': night_time_end if morning else line.time_to,
                        'day_id': line.day_id.id,
                        'prevent_deletion': line.prevent_deletion,
                        'holiday_id': line.holiday_id.id,
                    }
                    time_from = night_time_end if morning else line.time_from
                    vals_2 = {
                        'work_schedule_code_id': line.work_schedule_code_id.id,
                        'time_from': time_from,
                        'time_to': line.time_to if morning else night_time_start,
                        'day_id': line.day_id.id,
                        'prevent_deletion': line.prevent_deletion,
                        'holiday_id': line.holiday_id.id,
                    }
                    line.write({'time_from': time_from})
                    line_unlink_ids.append(line.id)
                    env_obj['work.schedule.day.line'].create(vals_1)
                    env_obj['work.schedule.day.line'].create(vals_2)
                else:
                    vals = {
                        'work_schedule_code_id': zymejimas_to_use.id,
                        'time_from': line.time_from,
                        'time_to': line.time_to,
                        'day_id': line.day_id.id,
                        'prevent_deletion': line.prevent_deletion,
                        'holiday_id': line.holiday_id.id,
                    }
                    line_unlink_ids.append(line.id)
                    env_obj['work.schedule.day.line'].create(vals)

        for rec in self:
            line_unlink_ids = []
            company = self.with_context(date=rec.date).env.user.company_id
            night_time_start = company.dn_start_time
            night_time_end = company.dn_end_time
            codes_not_valid_for_dn = ['BĮ', 'BN', 'DN']

            line_ids = rec.line_ids
            suitable_lines = line_ids.filtered(lambda l: l.code not in codes_not_valid_for_dn)
            evening_lines = suitable_lines.filtered(lambda l: l.time_to > night_time_start)
            morning_lines = suitable_lines.filtered(lambda l: l.time_from < night_time_end)
            create_night_lines(self.env, morning_lines)
            create_night_lines(self.env, evening_lines, morning=False)
            WorkScheduleDayLine.browse(line_unlink_ids).with_context(allow_delete_special=True).unlink()

    @api.multi
    def unlink(self):
        if any(line.prevent_modifying_as_past_planned for line in self.mapped('work_schedule_line_id')):
            raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))
        if any(rec.state != 'draft' for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti grafiko dienų, kurios nėra juodraščio būsenos.'))
        return super(WorkScheduleDay, self).unlink()

    @api.multi
    def open_main_setter(self):
        action = self.env.ref('work_schedule.action_open_main_schedule_setter').read()[0]
        context = ast.literal_eval(action['context'])
        context.update({'active_ids': self.ids})
        action['context'] = context
        return action

    @api.multi
    def open_overtime_setter(self):
        action = self.env.ref('work_schedule.action_open_overtime_schedule_setter').read()[0]
        context = ast.literal_eval(action['context'])
        context.update({'active_ids': self.ids})
        action['context'] = context
        return action

    @api.multi
    def open_absence_setter(self):
        action = self.env.ref('work_schedule.action_open_absence_schedule_setter').read()[0]
        context = ast.literal_eval(action['context'])
        context.update({'active_ids': self.ids})
        action['context'] = context
        return action

    @api.multi
    def open_holidays_setter(self):
        action = self.env.ref('work_schedule.action_open_holidays_schedule_setter').read()[0]
        context = ast.literal_eval(action['context'])
        if len(self.ids) != 1:
            raise exceptions.UserError(_('Norėdami užstatyti atostogas, turite pasirinkti tik pirmą atostogų dieną'))
        context.update({'active_ids': self.ids})
        action['context'] = context
        return action

    @api.model
    def get_wizard_view_id(self, model_name):
        if model_name == 'main.schedule.setter':
            return self.env.ref('work_schedule.main_work_schedule_setter_form').id
        elif model_name == 'overtime.schedule.setter':
            return self.env.ref('work_schedule.overtime_schedule_setter_form').id
        elif model_name == 'holidays.schedule.setter':
            return self.env.ref('work_schedule.holidays_schedule_setter_form').id
        elif model_name == 'new.work.schedule.day.wizard':
            return self.env.ref('work_schedule.new_schedule_line_wizard_form').id
        elif model_name == 'schedule.export.wizard':
            return self.env.ref('work_schedule.schedule_export_wizard_form').id
        elif model_name == 'jump.to.date.wizard':
            return self.env.ref('work_schedule.go_to_date_wizard_form').id
        else:
            raise exceptions.UserError(_('Neteisingai nurodytas veiksmas'))

    @api.multi
    def set_default_schedule_day_values(self):
        """
        Sets default values for given schedule days based on planned schedule days or the employee schedule template
        """
        if not self:
            return

        planned_company_schedule = self.env.ref('work_schedule.planned_company_schedule')
        overtime_marking = self.env.ref('work_schedule.work_schedule_code_VD')
        overtime_night_marking = self.env.ref('work_schedule.work_schedule_code_VDN',)
        overtime_on_holidays_marking = self.env.ref('work_schedule.work_schedule_code_VSS',)
        working_on_holidays_marking = self.env.ref('work_schedule.work_schedule_code_DP',)

        self.mapped('work_schedule_line_id').ensure_not_busy()

        # Delete all lines
        self.mapped('line_ids').filtered(lambda l: not l.matched_holiday_id and not l.holiday_id).unlink()

        line_values = []

        dates = list(set(self.mapped('date')))
        public_holiday_dates = self.env['sistema.iseigines'].search([('date', 'in', dates)]).mapped('date')
        min_date = min(dates)
        max_date = max(dates)

        employees = self.mapped('employee_id')

        # Find all appointments for employees and dates
        appointments = self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date_start', '<=', max_date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min_date)
        ])

        # Find all planned days
        planned_days = self.search([
            ('date', 'in', dates),
            ('employee_id', 'in', employees.ids),
            ('work_schedule_id', '=', planned_company_schedule.id),
            ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True)
        ])

        # Get all the work schedules time is being set for
        work_schedules_to_set_for = self.mapped('work_schedule_id')

        # Used to get day info from other departments
        all_days_for_dates = self.search([
            ('date', 'in', dates),
            ('employee_id', 'in', employees.ids),
            ('work_schedule_id', 'in', work_schedules_to_set_for.ids)
        ])

        # Get all work schedule codes - used for mapping tabelio.zymejimas to work.schedule.code later
        work_schedule_codes = self.env['work.schedule.codes'].sudo().search([])
        regular_day_marking = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')
        work_schedule_holiday_marking = self.env.ref('work_schedule.work_schedule_code_A')

        # Get forced work times
        forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date', '<=', max_date),
            ('date', '>=', min_date)
        ])

        full_downtimes = self.env['hr.employee.downtime'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date_from_date_format', '<=', max_date),
            ('date_to_date_format', '>=', min_date),
            ('holiday_id.state', '=', 'validate'),
            ('downtime_type', '=', 'full'),
        ])

        overtime_lines = self.env['hr.employee.overtime.time.line'].sudo().search([
            ('overtime_id.employee_id', 'in', employees.ids),
            ('date', '<=', max_date),
            ('date', '>=', min_date),
            ('overtime_id.state', '=', 'confirmed'),
        ])

        # Get day default data from schedule template
        schedule_templates = appointments.mapped('schedule_template_id')
        day_values_by_schedule_templates = schedule_templates._get_planned_time_ranges(dates)

        # Start looping by each work schedule type for ease
        for work_schedule in work_schedules_to_set_for:
            days_by_schedule = self.filtered(lambda d: d.work_schedule_id == work_schedule)
            employees = days_by_schedule.mapped('employee_id')
            for employee in employees:
                employee_department = employee.department_id
                employee_appointments = appointments.filtered(lambda app: app.employee_id == employee)
                employee_days_to_set = days_by_schedule.filtered(lambda d: d.employee_id == employee)
                employee_forced_work_days = forced_work_times.filtered(lambda d: d.employee_id == employee)
                forced_work_dates = employee_forced_work_days.mapped('date')
                all_employee_days = all_days_for_dates.filtered(lambda d: d.employee_id == employee)
                employee_overtime_lines = overtime_lines.filtered(lambda o: o.overtime_id.employee_id == employee)
                employee_full_downtimes = full_downtimes.filtered(lambda d: d.employee_id == employee)

                if work_schedule == planned_company_schedule:
                    # Make employee planned days empty so that no planned data is ever used if setting the default
                    # schedule day values for planned schedule
                    employee_planned_days = self.env['work.schedule.day']
                else:
                    employee_planned_days = planned_days.filtered(lambda d: d.employee_id == employee)

                for date in employee_days_to_set.mapped('date'):
                    appointment_for_date = employee_appointments.filtered(
                        lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date)
                    )
                    appointment_for_date = appointment_for_date and appointment_for_date[0]

                    date_overtime_lines = employee_overtime_lines.filtered(lambda d: d.date == date)
                    date_days_to_set = employee_days_to_set.filtered(lambda d: d.date == date)
                    all_employee_days_for_date = all_employee_days.filtered(lambda d: d.date == date)
                    days_to_keep = all_employee_days_for_date.filtered(lambda d: d.id not in date_days_to_set.ids)
                    # Get times already set in other departments
                    times_in_other_departments = [
                        (l.time_from, l.time_to, l.tabelio_zymejimas_id.id)
                        for l in days_to_keep.mapped('line_ids')
                    ]

                    full_downtime_for_date = employee_full_downtimes.filtered(
                        lambda downtime: downtime.date_from_date_format <= date <= downtime.date_to_date_format
                    )

                    is_forced_work_day_date = date in forced_work_dates

                    planned_days_for_date = employee_planned_days.filtered(lambda d: d.date == date)
                    if planned_days_for_date:
                        # Set times only for the days from planned schedule
                        days_to_set_time_for = date_days_to_set.filtered(
                            lambda d: d.department_id in planned_days_for_date.mapped('department_id')
                        )
                    elif appointment_for_date:
                        employee_department_day = date_days_to_set.filtered(
                            lambda d: d.department_id == employee_department
                        )
                        if employee_department_day:
                            # If there's a main department day to set time for in days to set then only set time for
                            # that main department day
                            days_to_set_time_for = employee_department_day
                        else:
                            # Otherwise only set time for one of the days for date (don't overlap default times)
                            days_to_set_time_for = date_days_to_set and date_days_to_set[0]
                    else:
                        continue

                    for day in days_to_set_time_for:
                        # To sum up the way that times are set follow:
                        # 1.Times already set in other departments
                        # 2.Non regular times that have been scheduled
                        # 3.Either planned times or scheduled times by schedule template

                        is_planned_schedule = day.work_schedule_id == planned_company_schedule

                        # Get default values from schedule template
                        schedule_template = appointment_for_date.schedule_template_id
                        scheduled_values = day_values_by_schedule_templates.get(
                            schedule_template.id, dict()
                        ).get(day.date, list()) if schedule_template else list()

                        # Find out which values of the values based on the schedule template are not regular. Those
                        # that were added from records such as overtime, downtime etc.
                        if any(
                                len(l) == 3 and l[2] == self.env.ref('l10n_lt_payroll.tabelio_zymejimas_PN').id
                                for l in scheduled_values
                        ):
                            values_not_regular = scheduled_values  # Downtime exists - all values not regular
                        else:
                            values_not_regular = [
                                l for l in scheduled_values if len(l) == 3 and l[2] != regular_day_marking.id
                            ]

                        # Get what was planned for that day
                        planned_day = planned_days_for_date.filtered(lambda d: d.department_id == day.department_id)
                        planned_day_values = [
                            (l.time_from, l.time_to, l.tabelio_zymejimas_id.id)
                            for l in planned_day.mapped('line_ids')
                        ]

                        # Check which values should be added.
                        # Force add scheduled values if day is full downtime since all values will be downtime values
                        if planned_day_values and not is_forced_work_day_date and not full_downtime_for_date:
                            values_to_add = planned_day_values
                        else:
                            values_to_add = scheduled_values

                        values_to_set = list()
                        if not is_forced_work_day_date:
                            # Adjust the non-regular values so that they don't overlap the times in other departments
                            values_not_regular = [
                                l for l in merge_line_values(times_in_other_departments, values_not_regular)
                                if l not in times_in_other_departments
                            ]
                            # They are the first values that should be set for the day
                            values_to_set = values_not_regular

                            # Make sure that the values being added do not overlap the non regular values that are
                            # scheduled
                            values_to_add = [
                                l for l in merge_line_values(values_not_regular, values_to_add)
                                if l not in values_not_regular
                            ]

                            # Get what other schedule or planned values should be set that don't overlap the times in
                            # other departments
                            values_to_add = [
                                l for l in merge_line_values(times_in_other_departments, values_to_add)
                                if l not in times_in_other_departments
                            ]
                        values_to_set = merge_line_values(values_to_set, values_to_add)

                        # Set said values
                        for values in values_to_set:
                            try:
                                marking = values[2]
                            except IndexError:
                                continue
                            # Match tabelio.zymejimas to work.schedule.code
                            matching_work_schedule_marking = work_schedule_codes.filtered(
                                lambda c: c.tabelio_zymejimas_id.id == marking
                            )
                            work_schedule_marking = matching_work_schedule_marking and matching_work_schedule_marking[0]

                            # Some lines might have holiday id set thus we should not try to create the lines on top of
                            # the existing lines
                            overlapping_line = any(
                                l.holiday_id or l.matched_holiday_id and
                                tools.float_compare(l.time_from, values[1], precision_digits=2) < 0 <
                                tools.float_compare(l.time_to, values[0], precision_digits=2)
                                for l in day.line_ids.exists()
                            )
                            if overlapping_line:
                                continue

                            prevent_deletion = is_forced_work_day_date
                            # Check if line is forced overtime line
                            if not prevent_deletion:
                                if date in public_holiday_dates:
                                    day_overtime_markings = [overtime_on_holidays_marking, working_on_holidays_marking]
                                else:
                                    day_overtime_markings = [overtime_marking, overtime_night_marking]
                                if work_schedule_marking in day_overtime_markings:
                                    prevent_deletion = any(
                                        tools.float_compare(line.time_from, values[1], precision_digits=2) < 0 <
                                        tools.float_compare(line.time_to, values[0], precision_digits=2)
                                        for line in date_overtime_lines
                                    )

                            is_holiday_line = work_schedule_marking == work_schedule_holiday_marking
                            if is_planned_schedule and is_holiday_line:
                                # Don't add holiday lines as lines for planned schedule day. If a holiday is set in the
                                # future - the planned day should not have any values what so ever. This only applies to
                                # cases where the planned line is created when a holiday already exists.
                                continue

                            line_values.append({
                                'day_id': day.id,
                                'time_from': values[0],
                                'time_to': values[1],
                                'work_schedule_code_id': work_schedule_marking.id,
                                'prevent_deletion': prevent_deletion
                            })

        for vals in line_values:
            self.env['work.schedule.day.line'].create(vals)

    @api.multi
    def _get_day_default_values(self):
        res = {}
        min_date = min(self.mapped('date'))
        max_date = max(self.mapped('date'))
        max_date_dt = datetime.strptime(max_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        next_day_after_max = (max_date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '>=', min_date),
            ('date', '<=', next_day_after_max)
        ]).mapped('date')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        planned_days = self.search([
            ('date', 'in', self.mapped('date')),
            ('work_schedule_id', '=', planned_schedule.id),
            ('department_id', 'in', self.mapped('department_id').ids),
            ('employee_id', 'in', self.mapped('employee_id').ids)
        ])
        regular_code = self.env.ref('work_schedule.work_schedule_code_FD')
        remote_code = self.env.ref('work_schedule.work_schedule_code_NT')
        dls_code = self.env.ref('work_schedule.work_schedule_code_DLS')

        dynamic_workplace_compensations_lines = self.env['hr.employee.compensation.time.line'].sudo().search([
            ('compensation_id.compensation_type', '=', 'dynamic_workplace'),
            ('compensation_id.compensation_time_ids', '!=', False),
            ('compensation_id.state', '=', 'confirm'),
            ('compensation_id.date_from', '<=', max_date),
            ('compensation_id.date_to', '>=', min_date),
            ('compensation_id.employee_id', 'in', self.mapped('employee_id').ids),
            ('date', '>=', min_date),
            ('date', '<=', max_date)
        ])

        for day in self:
            vals = []
            is_national_holiday = day.date in national_holiday_dates
            schedule_template_id = day.sudo().appointment_id.schedule_template_id
            if not day.appointment_id:
                res.update({day.id: []})
                continue
            day_date_dt = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            is_day_off = day_date_dt.weekday() in schedule_template_id.off_days()

            planned_day = day.work_schedule_id != planned_schedule and planned_days.filtered(
                lambda d: d.date == day.date and d.department_id.id == day.department_id.id and
                          d.employee_id.id == day.employee_id.id)
            if planned_day and not self._context.get('force_dont_use_planned'):
                # If planned day exist - we take the data from that date
                # TODO this does not shorten before holidays, maybe we should even if it was planned not to?
                vals = [(l.time_from, l.time_to, l.work_schedule_code_id.id) for l in planned_day.line_ids]
            elif not is_national_holiday and not is_day_off:
                # Based on regular schedule + shorter before holidays
                day_of_week_lines = schedule_template_id.fixed_attendance_ids.filtered(
                    lambda r: int(r.dayofweek) == day_date_dt.weekday())
                day_of_week_line_vals = []
                day_dynamic_workplace_compensations_lines = dynamic_workplace_compensations_lines.filtered(
                    lambda l: l.date == day.date
                )

                regular_work_time = [
                    (l.hour_from, l.hour_to, regular_code.id if not l.working_remotely else remote_code.id)
                    for l in day_of_week_lines.sorted(key=lambda l: l.hour_from)
                ]

                for dls_line in day_dynamic_workplace_compensations_lines:
                    time_from, time_to = dls_line.time_from, dls_line.time_to
                    if tools.float_compare(time_to, 0.0, precision_digits=2) == 0:
                        time_to = 24.0
                    day_of_week_line_vals.append((time_from, time_to, dls_code.id))

                for work_time in regular_work_time:
                    hour_from = work_time[0]
                    hour_to = work_time[1]
                    try:
                        code = work_time[2]
                    except IndexError:
                        code = regular_code.id
                    for dls_line in day_dynamic_workplace_compensations_lines:
                        time_from, time_to = dls_line.time_from, dls_line.time_to
                        if tools.float_compare(time_to, 0.0, precision_digits=2) == 0:
                            time_to = 24.0
                        overlap = time_from <= hour_from <= time_to or time_from <= hour_to <= time_to
                        if overlap:
                            if tools.float_compare(hour_from, time_from, precision_digits=2) <= 0:
                                if tools.float_compare(hour_to, time_to, precision_digits=2) > 0:
                                    regular_work_time.append((time_to, hour_to, code))
                                hour_to = min(hour_to, time_from)
                            elif tools.float_compare(hour_from, time_to, precision_digits=2) <= 0:
                                hour_from = time_to
                                hour_to = max(time_to, hour_to)
                    if tools.float_compare(hour_from, hour_to, precision_digits=2) != 0:
                        day_of_week_line_vals.append((hour_from, hour_to, code))

                if schedule_template_id.shorter_before_holidays:
                    next_day = (day_date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    if next_day in national_holiday_dates:
                        day_of_week_line_vals.sort(key=lambda l: l[1], reverse=True)
                        total_for_day = sum(l[1] - l[0] for l in day_of_week_line_vals)
                        to_subtract = min(total_for_day, 1.0)
                        for line_vals in day_of_week_line_vals:
                            line_total = line_vals[1] - line_vals[0]
                            max_to_subtract_for_line = min(line_total, to_subtract)
                            to_subtract -= max_to_subtract_for_line
                            new_line_total = (line_vals[1] - max_to_subtract_for_line) - line_vals[0]
                            if tools.float_compare(new_line_total, 0.0, precision_digits=2) > 0:
                                vals.append((line_vals[0], line_vals[0] + new_line_total))
                    else:
                        vals = day_of_week_line_vals
                else:
                    vals = day_of_week_line_vals

            res.update({day.id: vals})
        return res

    @api.model
    def calculate_special_hours(self, day_ids, contract=None):
        employee_id = day_ids.mapped('employee_id.id')
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        result = {}
        dp_times = {}
        dn_times = {}
        snv_times = {}
        result['DP'] = dp_times
        result['DN'] = dn_times
        result['SNV'] = snv_times
        national_holidays = self.env['sistema.iseigines'].search([('date', 'in', day_ids.mapped('date'))]).mapped('date')
        night_time_start = 22.0
        night_time_end = 6.0
        good_codes = ['DN', 'SNV', 'BĮ', 'BN']
        employee_contracts = self.env['hr.contract'].search([('employee_id', 'in', employee_id)])
        if contract:
            day_ids = day_ids.filtered(lambda d: d.contract_id == contract)
            contract_dates = list(set(day_ids.mapped('date')))
        else:
            contract_dates = list(set(day_ids.filtered(lambda d: d.contract_id).mapped('date')))
        all_lines = self.env['work.schedule.day.line'].search([
            ('date', 'in', contract_dates),
            ('employee_id', 'in', employee_id),
            ('code', 'in', good_codes),
            ('day_id.work_schedule_id', '=', factual_work_schedule.id)
        ])
        hr_holidays = self.env['hr.holidays']
        if contract_dates:
            hr_holidays = self.env['hr.holidays'].search([
                ('date_from', '<=', max(contract_dates)),
                ('date_to', '>=', min(contract_dates)),
                ('employee_id', 'in', employee_id),
                ('type', '=', 'remove'),
                ('state', '=', 'validate'),
                ('holiday_status_id.kodas', 'not in', ['K', 'MP', 'NLL'])
            ])
        for day_date in contract_dates:
            day_hr_holidays = hr_holidays.filtered(lambda h: h.date_from_date_format <= day_date <= h.date_to_date_format)
            todays_date = day_date
            todays_lines = all_lines.filtered(lambda l: l.date == todays_date)
            evening_lines = todays_lines.filtered(lambda l: l.time_to > night_time_start)
            morning_lines = todays_lines.filtered(lambda l: l.time_from < night_time_end)
            time_worked_night = sum(line.time_to - max(night_time_start, line.time_from) for line in evening_lines)
            time_worked_night += sum(min(night_time_end, line.time_to) - line.time_from for line in morning_lines)
            is_today_holiday = todays_date in national_holidays
            todays_employee_contract = employee_contracts.filtered(lambda c: c.date_start <= day_date and (not c.date_end or c.date_end >= day_date))
            todays_day_appointment = todays_employee_contract.with_context(date=day_date).appointment_id.id or False
            if is_today_holiday and not day_hr_holidays:
                if not snv_times.get(todays_day_appointment):
                    snv_times[todays_day_appointment] = {
                        'hours': 0.0,
                        'days': 0.0
                    }
                holiday_worked_time = sum(todays_lines.mapped('worked_time_total')) - time_worked_night
                snv_times[todays_day_appointment]['hours'] += time_worked_night
                snv_times[todays_day_appointment]['days'] += 1.0 if not tools.float_is_zero(time_worked_night, precision_digits=2) else 0.0
            else:
                if not dn_times.get(todays_day_appointment):
                    dn_times[todays_day_appointment] = {
                        'hours': 0.0,
                        'days': 0.0
                    }
                holiday_worked_time = 0.0
                dn_times[todays_day_appointment]['hours'] += time_worked_night
                dn_times[todays_day_appointment]['days'] += 1.0 if not tools.float_is_zero(time_worked_night, precision_digits=2) else 0.0
            if not dp_times.get(todays_day_appointment):
                dp_times[todays_day_appointment] = {
                    'hours': 0.0,
                    'days': 0.0
                }
            dp_times[todays_day_appointment]['hours'] += holiday_worked_time
            dp_times[todays_day_appointment]['days'] += 1.0 if not tools.float_is_zero(holiday_worked_time, precision_digits=2) else 0.0
        keys_to_pop = {}
        for zymejimas, data in iteritems(result):
            for app, app_data in iteritems(data):
                if not app or tools.float_is_zero(app_data['hours'] + app_data['days'], precision_digits=2):
                    if not keys_to_pop.get(zymejimas):
                        keys_to_pop[zymejimas] = []
                    keys_to_pop[zymejimas].append(app)

        for zymejimas in keys_to_pop:
            for app in keys_to_pop[zymejimas]:
                result[zymejimas].pop(app, None)
        return result

    @api.multi
    def write(self, vals):
        if any(line.prevent_modifying_as_past_planned for line in self.mapped('work_schedule_line_id')):
            raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))
        if not self.env.user.is_schedule_super():
            fill_department_ids = self.env.user.mapped('employee_ids.fill_department_ids.id')
            employee_ids = self.env.user.employee_ids.ids
            for rec in self:
                if 'work_schedule_line_id' in vals:
                    line = self.env['work.schedule.line'].browse(vals.get('work_schedule_line', False))
                else:
                    line = rec.work_schedule_line_id
                modifying_own_schedule = line and line.employee_id.id in employee_ids and line.employee_id.sudo().can_fill_own_schedule
                if line and ((line.department_id and line.department_id.id in fill_department_ids) or modifying_own_schedule):
                    super(WorkScheduleDay, rec.sudo()).write(vals)
                else:
                    super(WorkScheduleDay, rec).write(vals)
        else:
            super(WorkScheduleDay, self).write(vals)

    @api.multi
    def backup_days(self, raise_error=True):
        """
        Backs up given days.
        Args:
            raise_error (bool): raise error if the times would overlap when creating a back up or ignore the error and
            do not back up times for date
        """
        backup_schedule = self.env.ref('work_schedule.holiday_backup_schedule')

        if any(day.work_schedule_id == backup_schedule for day in self):
            if raise_error:
                raise exceptions.UserError(_('Can not back up days for back up schedule'))
            else:
                return

        employees = self.mapped('employee_id')
        dates = self.mapped('date')
        backup_days = self.env['work.schedule.day'].search([
            ('employee_id', 'in', employees.ids),
            ('date', 'in', dates),
            ('work_schedule_id', '=', backup_schedule.id)
        ])

        for rec in self:
            date = rec.date
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            backup_day = backup_days.filtered(lambda d: d.department_id == rec.department_id and
                                                        d.employee_id == rec.employee_id and
                                                        d.date == date)
            backup_day = backup_day and backup_day[0]
            if not backup_day:
                backup_schedule.create_empty_schedule(
                    date_dt.year,
                    date_dt.month,
                    employee_ids=[rec.employee_id.id],
                    department_ids=[rec.department_id.id]
                )
                backup_day = self.env['work.schedule.day'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('department_id', '=', rec.department_id.id),
                    ('date', '=', date),
                    ('work_schedule_id', '=', backup_schedule.id)
                ])

            if not backup_day:
                if raise_error:
                    raise exceptions.UserError(_('Backup day could not be created'))
                else:
                    continue

            backup_day.sudo().with_context(allow_delete_special=True).line_ids.unlink()

            for line in rec.line_ids:
                try:
                    line.copy({'day_id': backup_day.id})
                except Exception as e:
                    if raise_error:
                        raise e
                    else:
                        pass

    @api.multi
    def restore_data_from_backup_schedule(self, raise_error=True, force_restore=False):
        """
        Restores worked times from backup schedule for given days.
        Args:
            raise_error (bool): raise errors, for example when restored times would overlap
            force_restore (bool): force restore times by unlinking all times for date from other departments so that
            the work times not to overlap
        """
        backup_schedule = self.env.ref('work_schedule.holiday_backup_schedule')

        if any(day.work_schedule_id == backup_schedule for day in self):
            if raise_error:
                raise exceptions.UserError(_('Can not restore days for back up schedule'))
            else:
                return

        employees = self.mapped('employee_id')
        dates = self.mapped('date')
        backup_days = self.env['work.schedule.day'].search([
            ('employee_id', 'in', employees.ids),
            ('date', 'in', dates),
            ('work_schedule_id', '=', backup_schedule.id)
        ])

        for rec in self:
            date = rec.date
            backup_day = backup_days.filtered(lambda d: d.department_id == rec.department_id and
                                                        d.employee_id == rec.employee_id and
                                                        d.date == date)
            backup_day = backup_day and backup_day[0]
            if backup_day:
                rec.line_ids.unlink()
                try:
                    for line in backup_day.line_ids:
                        line.copy({'day_id': rec.id})
                except Exception as e:
                    if force_restore:
                        try:
                            related_days = rec.work_schedule_line_id.day_ids.filtered(lambda d: d.date == rec.date)
                            related_days.mapped('line_ids').unlink()
                            for line in backup_day.line_ids:
                                line.copy({'day_id': rec.id})
                        except Exception as e1:
                            if not raise_error:
                                pass
                            else:
                                raise e1
                    elif raise_error:
                        raise e
                    else:
                        pass


WorkScheduleDay()
