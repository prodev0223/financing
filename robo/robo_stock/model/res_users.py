# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    own_location_ids = fields.Many2many('stock.location', 'stock_location_res_users_rel',
                                        string='Own accepted locations', inverse='_set_own_location_ids',
                                        domain=[('usage', '=', 'internal')],
                                        groups='robo_basic.group_robo_premium_manager')

    location_ids = fields.Many2many('stock.location', 'res_users_stock_location_rel', string='Accepted locations',
                                    groups='robo_basic.group_robo_premium_manager')

    def _set_own_location_ids(self):
        for rec in self:
            for loc in rec.own_location_ids:
                loc._compute_user_ids()


ResUsers()
