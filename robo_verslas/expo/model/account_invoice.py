# -*- coding: utf-8 -*-
from odoo import models, api


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_sent(self):
        self.ensure_one()

        template = self.env.ref('expo.expo_main_account_invoice_template', raise_if_not_found=False)

        return super(AccountInvoice, self.with_context(force_template=template)).action_invoice_sent()


AccountInvoice()
