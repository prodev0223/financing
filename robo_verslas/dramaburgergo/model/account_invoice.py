# -*- coding: utf-8 -*-
from odoo import models, api


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        return super(AccountInvoice, self.with_context(skip_attachments=True)).action_invoice_open()


AccountInvoice()
