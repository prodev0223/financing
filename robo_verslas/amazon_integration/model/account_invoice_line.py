# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoiceLine(models.Model):
    """
    Model that holds methods/fields of account invoice lines used in amazon.integration
    """
    _inherit = 'account.invoice.line'

    amazon_order_line_ids = fields.One2many('amazon.order.line', 'invoice_line_id', string='Amazon užsakymų eilutės')


AccountInvoiceLine()
