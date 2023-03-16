# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountFiscalPositionTax(models.Model):
    _inherit = 'account.fiscal.position.tax'

    product_type = fields.Selection([('all', 'All'),
                                     ('product', 'Product'),
                                     ('service', 'Service')],
                                    string='Product Type', default='all', required=True)
