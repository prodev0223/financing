# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    amazon_sp_category_code = fields.Char(string='Category code')
