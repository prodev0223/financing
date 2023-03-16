# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, models


class InvoiceChangeTaxLineWizard(models.TransientModel):
    _inherit = 'invoice.change.tax.line.wizard'

    @api.multi
    def change_vals(self):
        invoice = self.tax_line_id.invoice_id
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if invoice_approval_is_active and invoice and invoice.state == 'in_approval':
            raise exceptions.UserError(_('You can not change invoice taxes at this time because the account invoice is '
                                         'being approved'))
        return super(InvoiceChangeTaxLineWizard, self).change_vals()
