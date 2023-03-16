# -*- coding: utf-8 -*-
from odoo import models, api


class StockInventory(models.Model):
    _inherit = 'stock.inventory'

    @api.model
    def get_base_product_domain(self):
        """Returns base product domain for inventory lines"""
        return [('type', '=', 'product'), ('r_keeper_pos_filter', '=', False)]
