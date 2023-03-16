# -*- coding: utf-8 -*-

from odoo import models, api


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    @api.onchange('product_id')
    def mo_onchange_product_id(self):
        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_konsignacija')])
        if rec and rec.state in ['installed', 'to upgrade'] and self.product_id.consignation and \
                self.invoice_id.type in ['in_invoice', 'in_refund']:
            account_id = self.env['account.account'].search([('code', '=', '6000')])
            self.account_id = account_id


AccountInvoiceLine()
