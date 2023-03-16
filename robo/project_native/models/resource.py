# -*- encoding: utf-8 -*-
from odoo import fields, models


class ResourceCalendar(models.Model):
    _name = 'resource.calendar'
    _inherit = 'resource.calendar'


    global_leave_ids = fields.One2many(
        'resource.calendar.leaves', 'calendar_id', string='Global Leaves',
        domain=[('resource_id', '=', False)]
        )


ResourceCalendar()
