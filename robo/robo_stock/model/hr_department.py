# -*- coding: utf-8 -*-
from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    default_stock_location_id = fields.Many2one('stock.location', string='Default inventory location',
                                                domain=[('usage', '=', 'internal')],
                                                groups='robo_basic.group_robo_premium_manager',
                                                inverse='_set_default_stock_location_id')

    def _set_default_stock_location_id(self):
        for rec in self:
            for member in rec.member_ids:
                member.user_id.location_ids._compute_user_ids()
            rec.default_stock_location_id._compute_user_ids()


HrDepartment()
