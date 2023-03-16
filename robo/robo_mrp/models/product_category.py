# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    default_production_location_id = fields.Many2one(
        'stock.location', string='Numatytoji žaliavų lokacija',
        domain=[('usage', '=', 'internal')]
    )
