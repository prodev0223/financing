# -*- coding: utf-8 -*-
from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.multi
    def get_mapped_moves(self, **_):
        """Method meant to be overridden in robo_stock"""
        self.ensure_zero_or_one()
        return self.env['stock.move']
