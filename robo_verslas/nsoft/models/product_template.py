# -*- coding: utf-8 -*-

from odoo import models, api, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    property_account_prime_cost_id = fields.Many2one('account.account', string='Savikainos sąskaita')

    @api.multi
    def create_variant_ids(self):
        for rec in self:
            super(ProductTemplate, rec.with_context(default_default_code=rec.default_code)).create_variant_ids()


ProductTemplate()
