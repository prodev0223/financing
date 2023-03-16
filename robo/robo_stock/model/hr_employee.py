# -*- coding: utf-8 -*-
from odoo import fields, models, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    department_id = fields.Many2one('hr.department', inverse='_set_department_id')

    @api.multi
    def _set_department_id(self):
        for rec in self:
            rec.user_id.location_ids._compute_user_ids()
            rec.department_id.default_stock_location_id._compute_user_ids()


HrEmployee()
