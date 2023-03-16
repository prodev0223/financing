# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class NewScheduleLineWizard(models.TransientModel):
    _name = 'new.schedule.line.wizard'

    def _current_year(self):
        return datetime.utcnow().year

    def _current_month(self):
        return str(datetime.utcnow().month)

    month = fields.Selection([('1', 'Sausis'), ('2', 'Vasaris'), ('3', 'Kovas'),
                               ('4', 'Balandis'), ('5', 'Gegužė'), ('6', 'Birželis'), ('7', 'Liepa'),
                               ('8', 'Rugpjūtis'), ('9', 'Rugsėjis'), ('10', 'Spalis'),
                               ('11', 'Lapkritis'), ('12', 'Gruodis')], string='Mėnuo', required=True, default=_current_month)
    year = fields.Integer(string='Metai', required=True, default=_current_year)
    schedule_id = fields.Many2one('work.schedule', string='Grafikas', required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    department_id = fields.Many2one('hr.department', string='Padalinys', required=True)

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        if self.employee_id and self.employee_id.department_id:
            self.department_id = self.employee_id.department_id

    @api.multi
    def confirm(self):
        line_amount = self.env['work.schedule.line'].search_count([
            ('employee_id', '=', self.employee_id.id),
            ('department_id', '=', self.department_id.id),
            ('work_schedule_id', '=', self.schedule_id.id),
            ('month', '=', int(self.month)),
            ('year', '=', self.year)
        ])
        if line_amount > 0:
            raise exceptions.UserError(_('Darbuotojo skyriaus eilute nurodytam periodui jau egzistuoja'))

        self.schedule_id.create_empty_schedule(self.year, int(self.month), [self.employee_id.id], [self.department_id.id])

    @api.model
    def default_get(self, field_list):
        res = super(NewScheduleLineWizard, self).default_get(field_list)
        month = self._context.get('month', False)
        year = self._context.get('year', False)
        work_schedule_id = self._context.get('work_schedule_id', False)
        if not self.env.user.is_schedule_super():
            res['department_id'] = self.env.user.mapped('employee_ids.department_id').id
        if not work_schedule_id:
            # Determine which schedule to use
            planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
            factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
            schedule_to_use = planned_schedule
            if year and month:
                period = datetime(year, month, 1)
                now = datetime.utcnow()
                schedule_to_use = factual_schedule if period <= now else planned_schedule
            res['schedule_id'] = schedule_to_use.id
        else:
            res['schedule_id'] = work_schedule_id
        if month:
            res['month'] = str(month)
        if year:
            res['year'] = year
        return res

    @api.model
    def create(self, vals):
        res = super(NewScheduleLineWizard, self).create(vals)
        if self._context.get('auto_confirm', True):
            res.confirm()
        return res


NewScheduleLineWizard()
