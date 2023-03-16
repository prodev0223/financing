# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    ebay_order_line_ids = fields.One2many(
        'ebay.order.line', 'invoice_line_id', string='eBay order lines',
    )
