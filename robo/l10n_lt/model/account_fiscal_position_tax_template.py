# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountFiscalPositionTaxTemplate(models.Model):
    _inherit = 'account.fiscal.position.tax.template'

    product_type = fields.Selection([('all', 'All'),
                                     ('product', 'Product'),
                                     ('service', 'Service')],
                                    string='Product Type', default='all', required=True)
