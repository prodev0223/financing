# -*- coding: utf-8 -*-
from odoo import models, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.multi
    def find_matching_tax_varying_settings(self, type_tax_use, price_include=True):
        """
        Find matching account tax record based on code, but with varying settings
        type_tax_use and price_include
        :param type_tax_use: sale/purchase - Signifies tax type based on invoice
        :param price_include: True/False - Signifies whether price is included in tax
        :return: account.tax record
        """
        self.ensure_one()
        account_tax = self.env['account.tax'].search([
            ('code', '=', self.code),
            ('type_tax_use', '=', type_tax_use),
            ('price_include', '=', price_include)], limit=1)
        return account_tax


AccountTax()
