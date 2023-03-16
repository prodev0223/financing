# coding=utf-8
from odoo import models, fields, api


class DefaultScheduleTemplateSetter(models.TransientModel):
    _name = 'default.schedule.template.setter'

    def _schedule_template_id(self):
        return self._context.get('schedule_template_id')

    schedule_template_id = fields.Many2one('schedule.template', required=True, default=_schedule_template_id)

    @api.one
    def set_default_schedule_values(self):
        self.schedule_template_id.set_regular_schedule_values(start_at_9_am=self._context.get('start_at_9_am', False))


DefaultScheduleTemplateSetter()
