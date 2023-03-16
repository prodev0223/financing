# -*- coding: utf-8 -*-


from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'
    _order = 'sequence, default_code, id'

    # Agreed on module and field naming - Will be used for internal,
    # and it has to be defined in Robo
    r_keeper_pos_filter = fields.Boolean()
