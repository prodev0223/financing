# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    r_keeper_pos_filter = fields.Boolean(string='Filtruojamas rKeeper kasos produktas')
