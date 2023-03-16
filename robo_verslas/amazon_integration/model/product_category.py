# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductCategory(models.Model):
    """
    Add required product code to category
    """
    _inherit = 'product.category'

    code = fields.Char(string='Kategorijos kodas')


ProductCategory()
