# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions


class AccountInvoiceVatChangeWizard(models.TransientModel):
    """
    Wizard that is used to change invoice line tax ids
    on every current invoice line
    """
    _name = 'account.invoice.vat.change.wizard'

    def get_account_tax_domain(self):
        invoice = self.env['account.invoice'].browse(self._context.get('active_id'))
        domain = [('price_include', '=', invoice.price_include)]
        if invoice.type in ['out_invoice', 'out_refund']:
            domain.append(('type_tax_use', '=', 'sale'))
        else:
            domain.append(('type_tax_use', '=', 'purchase'))
        return domain

    account_tax_id = fields.Many2one('account.tax', string='Account tax',
                                     domain=lambda self: self.get_account_tax_domain())

    @api.multi
    def change_taxes(self):
        """
        Method that replaces taxes of all invoice lines to the selected tax;
        """
        self.ensure_one()
        active_id = self._context.get('active_id')
        invoice = self.env['account.invoice'].browse(active_id)
        if invoice.force_taxes:
            raise exceptions.ValidationError(_('You can not change taxes for invoices that have forced taxes enabled'))
        invoice.invoice_line_ids.write({'invoice_line_tax_ids': [(6, 0, self.account_tax_id.ids)]})
        # Cancel, draft, open the invoice for values to recompute;
        invoice.action_invoice_cancel()
        invoice.action_invoice_draft()
        invoice.action_invoice_open()
