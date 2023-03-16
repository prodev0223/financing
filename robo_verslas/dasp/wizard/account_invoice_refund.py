# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountInvoiceRefund(models.TransientModel):
    _inherit = 'account.invoice.refund'

    description = fields.Char(default='grąžinimas')


AccountInvoiceRefund()
