# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    amazon_sp_order_line_ids = fields.One2many(
        'amazon.sp.order.line', 'invoice_line_id', string='Amazon order lines'
    )
