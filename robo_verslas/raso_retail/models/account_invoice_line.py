# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    raso_sale_line_id = fields.Many2one('raso.sales',  string='Raso pardavimo eilutė', inverse='mark_sale_line')
    raso_inv_line_id = fields.Many2one('raso.invoices.line', string='Raso saskaitos eilutė', inverse='mark_inv_line')

    @api.one
    def mark_sale_line(self):
        sale = self.env['raso.sales'].sudo().search([('id', '=', self.raso_sale_line_id.id)], limit=1)
        sale.write({'invoice_line_id': self.id})

    @api.one
    def mark_inv_line(self):
        sale = self.env['raso.invoices.line'].sudo().search([('id', '=', self.raso_inv_line_id.id)], limit=1)
        sale.write({'invoice_line_id': self.id})
