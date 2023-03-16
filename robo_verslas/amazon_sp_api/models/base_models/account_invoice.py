# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    amazon_sp_order_id = fields.Many2one(
        'amazon.sp.order', string='Amazon order'
    )
