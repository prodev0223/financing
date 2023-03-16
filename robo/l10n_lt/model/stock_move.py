# -*- coding: utf-8 -*-
from odoo import models, fields


class StockMove(models.Model):
    _inherit = 'stock.move'

    price_unit = fields.Float(group_operator='product_uom_qty', digits=(16, 16))
