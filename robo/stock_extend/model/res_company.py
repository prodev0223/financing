# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    allow_zero_value_quant = fields.Boolean(string='Leisti produktus su nuline verte')
    allow_consumable_products = fields.Boolean(groups='base.group_system')
