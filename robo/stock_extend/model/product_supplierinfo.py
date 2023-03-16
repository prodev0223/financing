# -*- coding: utf-8 -*-
from odoo import models, api, fields, _


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    @api.onchange('product_code', 'product_name')
    def onchange_product_code_name(self):
        if self.product_code:
            self.product_code = self.product_code.strip()
        if self.product_name:
            self.product_name = self.product_name.strip()

