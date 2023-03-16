# -*- coding: utf-8 -*-

from odoo import api, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def get_account_invoice_mail_template(self):
        """
        Overrides the base method and calls super with force_use_old_invoice_mail_template in context to force use the
        old 'account.email_template_edi_invoice' account invoice mail template. This is due to the client specific
        changes made to the template.
        template
        Args:
            language (string): (optional) language ISO code to get the template based on language

        Returns:
            Mail template to use for sending the invoice
        """
        return super(
            AccountInvoice,
            self.with_context(force_use_old_invoice_mail_template=True)
        ).get_account_invoice_mail_template()


AccountInvoice()
