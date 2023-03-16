# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BatteryLineRemoveWizard(models.TransientModel):
    _name = 'battery.line.remove.wizard'

    product_id = fields.Many2one('product.template', string='Produktas', readonly=True)
    product_battery_line_ids = fields.Many2many('product.battery.line', string='Trinamos baterijų eilutės',
                                                domain="[('product_tmpl_id','=',product_id)]")
    num_lines = fields.Integer(compute='_num_lines')

    @api.one
    @api.depends('product_battery_line_ids')
    def _num_lines(self):
        self.num_lines = len(self.product_battery_line_ids)

    @api.one
    def action_delete_lines(self):
        self.product_battery_line_ids.sudo().unlink()
