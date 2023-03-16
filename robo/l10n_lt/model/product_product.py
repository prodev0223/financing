# -*- coding: utf-8 -*-
from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def get_default_account(self):
        account_id = self.env['account.account'].search([('code', '=', '631299')])
        if account_id:
            return account_id.id
        else:
            return False

    @api.multi
    def set_default_product_category(self):
        for rec in self:
            if rec.type == 'product':
                rec.categ_id = self.env.ref('l10n_lt.product_category_1').id
            else:
                rec.categ_id = self.env.ref('l10n_lt.product_category_23').id
