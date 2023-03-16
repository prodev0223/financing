# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _


class BaseScheduleSetter(models.TransientModel):
    _name = 'base.schedule.setter'

    def default_day_schedule_ids(self):
        return [(6, 0, self._context.get('active_ids'))]

    day_schedule_ids = fields.Many2many('work.schedule.day', default=default_day_schedule_ids)

    @api.multi
    @api.constrains('day_schedule_ids')
    def _check_days_selected(self):
        for rec in self:
            if not rec.day_schedule_ids:
                raise exceptions.UserError(_('Nepasirinkote jokių dienų'))
            rec.day_schedule_ids.check_state_rules()
            if len(set(rec.day_schedule_ids.mapped('work_schedule_id.id'))) > 1:
                raise exceptions.UserError(_('Galima keisti tik vieno grafiko dienas vienu metu.'))

    @api.multi
    def check_rights_to_modify(self):
        self.ensure_one()
        self.day_schedule_ids.check_state_rules()

    @api.model
    def default_get(self, field_list):
        res = super(BaseScheduleSetter, self).default_get(field_list)
        day_ids = self.env['work.schedule.day'].browse(self._context.get('active_ids', []))
        if not day_ids:
            raise exceptions.UserError(_('Nepasirinkote jokių dienų'))
        day_ids.check_state_rules()
        return res

BaseScheduleSetter()











