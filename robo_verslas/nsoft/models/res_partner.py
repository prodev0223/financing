# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):

    _inherit = 'res.partner'

    forced_nsoft_purchase_tax_id = fields.Many2one(
        'account.tax', string='Priverstinis nSoft pirkimo sąskaitų PVM',
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'purchase')]"
    )
