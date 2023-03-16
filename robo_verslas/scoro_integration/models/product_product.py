# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    scoro_external_id = fields.Integer(string='Išorinis Scoro ID')


ProductProduct()
