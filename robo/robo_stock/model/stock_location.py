# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class StockLocation(models.Model):
    _inherit = 'stock.location'

    own_user_ids = fields.Many2many('res.users', 'stock_location_res_users_rel', string='Own accepted users', inverse='_set_own_user_ids',
                                    groups='robo_basic.group_robo_premium_manager')
    user_ids = fields.Many2many('res.users', 'res_users_stock_location_rel', string='Accepted users',
                                compute='_compute_user_ids', store=True,
                                groups='robo_basic.group_robo_premium_manager')
    department_ids = fields.One2many('hr.department', 'default_stock_location_id')

    @api.multi
    def name_get(self):
        return super(StockLocation, self.sudo()).name_get()

    @api.depends('own_user_ids', 'location_id.own_user_ids', 'location_id.user_ids')
    def _compute_user_ids(self):
        for rec in self.filtered(lambda l: l.usage == 'internal'):
            department_user_ids = rec.department_ids.mapped('member_ids.user_id.id')
            user_ids = (rec.location_id and rec.location_id.user_ids.ids or []) + rec.own_user_ids.ids + department_user_ids
            rec.user_ids = [(6, 0, user_ids)]

    def _set_own_user_ids(self):
        for rec in self.filtered(lambda l: l.usage == 'internal'):
            children_ids = self.env['stock.location'].search([('location_id', '=', rec.id)])
            for child in children_ids:
                child._compute_user_ids()
                child._set_own_user_ids()

    @api.model
    def get_default_location(self):
        """Returns oldest internal stock location"""
        return self.sudo().env['stock.location'].search(
            [('usage', '=', 'internal')], order='id asc', limit=1)


StockLocation()
