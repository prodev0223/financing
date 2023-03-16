# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, models


class AccountInvoicePartnerChangeWizard(models.TransientModel):
    _inherit = 'account.invoice.partner.change.wizard'

    @api.multi
    def change_partner_id(self):
        self.ensure_one()
        invoice = self.invoice_id
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if not invoice_approval_is_active or not invoice.approved:
            return super(AccountInvoicePartnerChangeWizard, self).change_partner_id()
        else:
            raise exceptions.UserError(_('You can not perform this action since the invoice has already been approved'))


AccountInvoicePartnerChangeWizard()
