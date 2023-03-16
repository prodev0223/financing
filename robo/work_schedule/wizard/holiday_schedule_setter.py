# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class HolidaysScheduleSetter(models.TransientModel):
    _name = 'holidays.schedule.setter'
    _inherit = 'base.schedule.setter'


    def domain_work_schedule_code_id(self):
        absence_is_being_set = self._context.get('is_absence_setter', False)
        domain = '['
        if absence_is_being_set:
            domain += '''('is_absence', '=', True)'''
        else:
            domain += '''('is_holiday', '=', True)'''
        if not self.env.user.is_accountant():
            domain += ''',('can_only_be_set_by_accountants', '=', False)'''
        domain += ']'
        return domain

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete='cascade', readonly=True)
    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki', required=True)
    work_schedule_code_id = fields.Many2one("work.schedule.codes", string="Atostogų tipas", required=True,
                                        ondelete='cascade', domain=domain_work_schedule_code_id)
    selected_existing_holidays = fields.Boolean(compute='_compute_selected_existing_holidays')


    @api.one
    @api.depends('day_schedule_ids', 'date_from', 'date_to')
    def _compute_selected_existing_holidays(self):
        if self.day_schedule_ids.mapped('schedule_holiday_id'):
            self.selected_existing_holidays = True

    @api.model
    def check_setter_constraints(self, day_ids):
        holidays_selected = day_ids.mapped('schedule_holiday_id')
        if len(holidays_selected) > 1:
            raise exceptions.UserError(_('Pasirinktuose dienų įrašuose egzistuoja keli atostogų įrašai, prašome pasirinkti kiekvieno atostogų įrašo dienas atskirai.'))
        elif holidays_selected:
            holidays_selected.mapped('day_ids').check_state_rules()

        employee_id = day_ids.mapped('employee_id.id')
        if len(employee_id) > 1:
            raise exceptions.UserError(_('Atostogos turi būti nustatomos vienam darbuotojui'))

        self.env['work.schedule.day'].search([
            ('employee_id', '=', employee_id[0]),
            ('date', '<=', self.date_to),
            ('date', '>=', self.date_from),
            ('work_schedule_id', 'in', day_ids.mapped('work_schedule_id.id'))
        ]).check_state_rules()


    @api.multi
    def confirm(self):
        self.ensure_one()
        self.mapped('day_schedule_ids.work_schedule_line_id').ensure_not_busy()
        self.check_rights_to_modify()
        days_to_check_rules_for = self.day_schedule_ids
        self.check_setter_constraints(days_to_check_rules_for)

        holiday_status = self.env['hr.holidays.status'].search(
            [('tabelio_zymejimas_id.id', '=', self.work_schedule_code_id.tabelio_zymejimas_id.id)], limit=1)
        if not self.selected_existing_holidays:
            self.env['work.schedule.holidays'].create({
                'date_from': self.date_from,
                'date_to': self.date_to,
                'holiday_status_id': holiday_status.id,
                'employee_id': self.employee_id.id,
            })
        else:
            self.day_schedule_ids.mapped('schedule_holiday_id').unlink()

    @api.model
    def default_get(self, field_list):
        res = super(HolidaysScheduleSetter, self).default_get(field_list)
        day_ids = self.env['work.schedule.day'].browse(self._context.get('active_ids', []))
        self.check_setter_constraints(day_ids)
        holidays_selected = day_ids.mapped('schedule_holiday_id')
        employee_id = day_ids.mapped('employee_id.id')
        if 'employee_id' in field_list:
            res['employee_id'] = employee_id[0]
        if 'date_from' in field_list:
            res['date_from'] = holidays_selected.date_from or min(day_ids.mapped('date'))
        if 'date_to' in field_list:
            res['date_to'] = holidays_selected.date_to or max(day_ids.mapped('date'))
        if 'work_schedule_code_id' in field_list:
            res['work_schedule_code_id'] = self.env['work.schedule.codes'].search([('tabelio_zymejimas_id', '=', holidays_selected.holiday_status_id.tabelio_zymejimas_id.id)]).id
        return res


HolidaysScheduleSetter()