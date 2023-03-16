# -*- coding: utf-8 -*-
from odoo import models, api


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def get_account_invoice_mail_template(self):
        """
        Gets the mail template for account invoice based on UX settings, ignoring the forced template because the user
        might have adjusted the mail template manually through UX settings from what it was hardcoded for them.
        Args:
            language (string): (optional) language ISO code to get the template based on language

        Returns:
            Mail template to use for sending the invoice
        """
        template = None

        if self._context.get('force_use_old_invoice_mail_template'):
            # Force use default (old) template. Useful for client modules that have changes to this template.
            template = self.env.ref('account.email_template_edi_invoice', False)
        else:
            company = self.env.user.company_id
            settings = company.sudo().robo_ux_settings_id
            if settings and settings.enabled:
                # Try to get the template from ux settings
                language = self._context.get('lang', 'lt_LT')
                if language == 'lt_LT':
                    template = settings.invoice_mail_template_lt_id
                else:
                    template = settings.invoice_mail_template_en_id

        if template:
            return template
        else:
            return super(AccountInvoice, self).get_account_invoice_mail_template()


AccountInvoice()
