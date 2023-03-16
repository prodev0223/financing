# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models
from odoo.tools.translate import _


class WorkScheduleHolidays(models.Model):
    _name = 'work.schedule.holidays'

    date_from = fields.Date(string='Pradžios data', required=True)
    date_to = fields.Date(string='Pabaigos data', required=True)
    day_ids = fields.One2many('work.schedule.day', string='Susijusios dienos', compute='_compute_day_ids')
    holiday_status_id = fields.Many2one("hr.holidays.status", string="Atostogų tipas", required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    holiday_id = fields.Many2one('hr.holidays', string='Holiday', compute='_compute_holiday_id')
    is_confirmed = fields.Boolean(string='Patvirtinta', compute='_compute_is_confirmed')

    @api.multi
    def name_get(self):
        return [(rec.id, '%s %s' % (rec.employee_id.name, rec.holiday_status_id.name)) for rec in self]

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id')
    def _compute_day_ids(self):
        for rec in self:
            rec.day_ids = self.env['work.schedule.day'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '<=', rec.date_to),
                ('date', '>=', rec.date_from)
            ]).mapped('id')

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id', 'holiday_status_id')
    def _compute_holiday_id(self):
        holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('date_from_date_format', '<=', max(self.mapped('date_to'))),
            ('date_to_date_format', '>=', min(self.mapped('date_from'))),
            ('holiday_status_id', 'in', self.mapped('holiday_status_id').ids)
        ])
        for rec in self:
            related_holidays = holidays.filtered(
                lambda h: h.date_from_date_format == rec.date_from and h.date_to_date_format == rec.date_to and
                          h.employee_id == rec.employee_id and h.holiday_status_id == rec.holiday_status_id
            )
            rec.holiday_id = related_holidays and related_holidays[0]

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id', 'holiday_status_id')
    def _compute_is_confirmed(self):
        for rec in self:
            rec.is_confirmed = rec.holiday_id

    @api.multi
    @api.constrains('date_from', 'date_to', 'holiday_status_id', 'employee_id')
    def _check_date(self):
        poilsio_type_id = self.env.ref('hr_holidays.holiday_status_P', raise_if_not_found=False)
        poilsio_type_id = poilsio_type_id and poilsio_type_id.id or False
        for schedule_holiday_id in self.filtered(lambda r: r.holiday_status_id.id != poilsio_type_id):
            domain = [
                ('date_from', '<=', schedule_holiday_id.date_to),
                ('date_to', '>=', schedule_holiday_id.date_from),
                ('employee_id', '=', schedule_holiday_id.employee_id.id),
                ('id', '!=', schedule_holiday_id.id),
                ('holiday_status_id', '!=', poilsio_type_id),
            ]
            nholidays = self.env['work.schedule.holidays'].search_count(domain)
            if nholidays > 0:
                raise exceptions.ValidationError(_('Negalima turėti persidengiančių atostogų'))

    @api.multi
    def unlink(self, bypass_confirmed=False, raise_error=False, holiday_id_being_created=False, remove_confirmed=False):
        self.mapped('day_ids.work_schedule_line_id').ensure_not_busy()

        user = self.env.user
        user_employees = user.employee_ids

        user_is_manager = user.is_schedule_manager()
        user_is_accountant = user.is_accountant()

        business_trip_holiday_status = self.env.ref('hr_holidays.holiday_status_K')
        factual_company_schedule = self.env.ref('work_schedule.factual_company_schedule')

        for rec in self:
            affected_days = rec.day_ids
            affected_departments = affected_days.mapped('work_schedule_line_id.department_id')
            affected_employee = rec.employee_id

            modifying_own_schedule = affected_employee.sudo().can_fill_own_schedule and \
                                     affected_employee in user_employees
            can_modify_selected_departments = user.can_modify_schedule_departments(affected_departments.ids)

            if not user_is_manager and not can_modify_selected_departments and not modifying_own_schedule:
                raise exceptions.UserError(_('Neturite teisės ištrinti atostogų iš visų skyrių'))

            schedule_is_confirmed = 'done' in affected_days.mapped('state')
            holiday_record_exists = rec.holiday_id
            is_business_trip = rec.holiday_status_id == business_trip_holiday_status

            if not is_business_trip and not bypass_confirmed and (holiday_record_exists or schedule_is_confirmed):
                raise exceptions.ValidationError(_('Negalima ištrinti patvirtintų atostogų'))

            existing_holiday = holiday_record_exists
            if holiday_id_being_created:
                existing_holiday = existing_holiday.filtered(lambda h: h.id != holiday_id_being_created)

            if existing_holiday and not remove_confirmed and not is_business_trip:
                if not raise_error:
                    continue
                elif user_is_accountant:
                    raise exceptions.UserError(_('Šios atostogos buvo sukurtos iš sistemos, todėl negalima jų ištrinti'))
                else:
                    raise exceptions.UserError(_('Negalima ištrinti patvirtintų atostogų'))

            departments_user_can_edit = user.get_departments_user_can_edit()
            allow_unlink = not affected_days or \
                           any(department in departments_user_can_edit for department in affected_departments) or \
                           modifying_own_schedule

            if allow_unlink:
                day_ids = rec.day_ids.filtered(lambda d: d.work_schedule_id == factual_company_schedule)
                super(WorkScheduleHolidays, rec.sudo()).unlink()
                if day_ids:
                    day_ids.filtered(lambda d: not d.line_ids).set_default_schedule_day_values()
            else:
                raise exceptions.UserError(_('Neturite teisės ištrinti šio neatvykimo'))

    @api.model
    def create(self, vals):
        employee_id = self.env['hr.employee'].browse(vals.get('employee_id', False))
        date_from = vals.get('date_from', False)
        date_to = vals.get('date_to', False)
        user = self.env.user
        if employee_id and date_from and date_to:
            day_ids = self.env['work.schedule.day'].search([
                ('employee_id', '=', employee_id.id),
                ('date', '<=', date_to),
                ('date', '>=', date_from)
            ])
            line_holidays_exist = any(day.mapped('line_ids').filtered(lambda l: l.holiday_id) for day in day_ids)
            if line_holidays_exist:
                raise exceptions.UserError(_('Can not create work schedule holidays for the selected days because '
                                             'a system leave already exists.'))
            affected_departments = day_ids.mapped('department_id')

            departments_user_can_edit = user.get_departments_user_can_edit()

            modifying_own_schedule = employee_id.sudo().can_fill_own_schedule and employee_id in user.employee_ids
            user_can_edit_at_least_some_departments = bool(departments_user_can_edit)
            schedule_does_not_exist = not day_ids
            user_manages_at_least_one_department = any(dep in departments_user_can_edit for dep in affected_departments)

            create_with_sudo = user_manages_at_least_one_department or modifying_own_schedule or \
                               (user_can_edit_at_least_some_departments and schedule_does_not_exist)

            if create_with_sudo:
                return super(WorkScheduleHolidays, self.sudo()).create(vals)
            else:
                return super(WorkScheduleHolidays, self).create(vals)
        else:
            return super(WorkScheduleHolidays, self).create(vals)


WorkScheduleHolidays()
