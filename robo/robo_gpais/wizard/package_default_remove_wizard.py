# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PackageDefaultRemoveWizard(models.TransientModel):
    _name = 'package.default.remove.wizard'

    product_id = fields.Many2one('product.template', string='Produktas', readonly=True)
    package_line_ids = fields.Many2many('product.package.default', string='Trinamos pakuočių eilutės',
                                        domain="[('product_tmpl_id','=',product_id)]")
    num_lines = fields.Integer(compute='_num_lines')

    @api.one
    @api.depends('package_line_ids')
    def _num_lines(self):
        self.num_lines = len(self.package_line_ids)

    @api.one
    def action_delete_lines(self):
        self.package_line_ids.sudo().unlink()
