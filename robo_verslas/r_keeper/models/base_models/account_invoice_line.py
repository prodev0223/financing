# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    r_keeper_sale_line_ids = fields.One2many(
        'r.keeper.sale.line', 'invoice_line_id',
        string='rKeeper pardavimo eilutės'
    )
