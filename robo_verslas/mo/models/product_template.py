# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def default_product_code(self):
        return self.env['ir.sequence'].next_by_code("MO_PRODUCT_CODE")

    default_code = fields.Char(default=default_product_code)


ProductTemplate()
