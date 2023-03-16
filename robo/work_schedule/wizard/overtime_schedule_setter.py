# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, exceptions
from odoo.tools.translate import _


class OvertimeScheduleSetter(models.TransientModel):
    _name = 'overtime.schedule.setter'
    _inherit = 'base.schedule.setter'

    def default_overtime_code(self):
        return self.env.ref('work_schedule.work_schedule_code_VD')

    def domain_work_schedule_code_id(self):
        if self.env.user.is_accountant():
            return "[('is_overtime', '=', True)]"
        else:
            return "[('is_overtime', '=', True), ('can_only_be_set_by_accountants', '=', False)]"

    work_hours_from = fields.Float(string='Laikas nuo')
    work_hours_to = fields.Float(string='Laikas iki')
    work_schedule_code_id = fields.Many2one('work.schedule.codes', string='Žymėjimas', required=True,
                                           default=default_overtime_code, ondelete='cascade',
                                           domain=domain_work_schedule_code_id)
    whole_day = fields.Boolean(compute='_compute_whole_day')

    @api.one
    @api.depends('work_schedule_code_id')
    def _compute_whole_day(self):
        self.whole_day = True if self.work_schedule_code_id.is_whole_day else False

    def check_work_hour_constraints(self):
        if tools.float_compare(self.work_hours_from, self.work_hours_to, precision_digits=3) > 0:
            raise exceptions.UserError(_('Darbo pradžia turi būti prieš darbo pabaigą'))

    @api.model
    def default_get(self, fields_list):
        res = super(OvertimeScheduleSetter, self).default_get(fields_list)
        work_hours_from = 0.0
        work_hours_to = 0.0
        day_ids = self.env['work.schedule.day'].browse(self._context.get('active_ids', []))
        if day_ids:
            day_ids_with_lines = day_ids.filtered(lambda d: len(d.line_ids) > 0)
            if day_ids_with_lines:
                sample_day = day_ids_with_lines[0]
                last_sample_day_line = sample_day.line_ids.sorted(key='time_from', reverse=True)[0]
                work_hours_from = last_sample_day_line.time_to
                work_hours_to = min(last_sample_day_line.time_to + 1, 24)
        if 'work_hours_from' in fields_list:
            res['work_hours_from'] = work_hours_from
        if 'work_hours_to' in fields_list:
            res['work_hours_to'] = work_hours_to
        return res

    @api.multi
    def confirm(self):
        self.ensure_one()
        self.mapped('day_schedule_ids.work_schedule_line_id').ensure_not_busy()
        self.check_rights_to_modify()
        self.check_work_hour_constraints()
        main_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        self.mapped('day_schedule_ids').filtered(
            lambda d: d.work_schedule_line_id.work_schedule_id.id != main_work_schedule.id).mapped(
            'schedule_holiday_id').unlink()
        vals = {
            'time_from': self.work_hours_from,
            'time_to': self.work_hours_to,
            'work_schedule_code_id': self.work_schedule_code_id.id
        }
        if self.whole_day:
            vals['time_from'] = 0.0
            vals['time_to'] = 24.0
        line_commands = [(0, 0, vals)]
        self.day_schedule_ids.write({'line_ids': line_commands})


OvertimeScheduleSetter()