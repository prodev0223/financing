# -*- coding: utf-8 -*-
from odoo import models, fields


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    product_uom_id = fields.Many2one(store=True)


StockQuant()
