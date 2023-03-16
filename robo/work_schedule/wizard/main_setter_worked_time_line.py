# -*- coding: utf-8 -*-

from odoo import api, fields, models


class MainSetterWorkedTimeLine(models.TransientModel):

    _name = 'main.setter.worked.time.line'

    def get_default_zymejimas(self):
        return self.env.ref('work_schedule.work_schedule_code_FD')

    def domain_work_schedule_code_id(self):
        domain = ['|', ('is_overtime', '=', True), ('is_whole_day', '=', False)]
        if not self.env.user.is_accountant():
            domain.append(('can_only_be_set_by_accountants', '=', False))
        return str(domain)

    main_schedule_setter_id = fields.Many2one('main.schedule.setter', string='Vedlys', required=True, ondelete='cascade')
    time_from = fields.Float('Pradžios laikas', required=True)
    time_to = fields.Float('Pabaigos laikas', required=True)
    work_schedule_code_id = fields.Many2one('work.schedule.codes', string='Žymėjimas', default=get_default_zymejimas, required=True, domain=domain_work_schedule_code_id, ondelete='cascade')
    time_total = fields.Float(string='Laiko suma', compute='_compute_time_amount')

    @api.one
    @api.depends('time_from', 'time_to', 'main_schedule_setter_id')
    def _compute_time_amount(self):
        self.time_total = self.time_to - self.time_from


MainSetterWorkedTimeLine()