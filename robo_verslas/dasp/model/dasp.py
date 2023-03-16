# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def default_price_include_selection(self):
        if self._context.get('type', 'in_invoice') in ['out_invoice', 'out_refund']:
            return 'inc'
        else:
            return 'exc'

    commercial_offer = fields.Selection([('taip', 'Taip'), ('ne', 'Ne')], string='Komercinis pasiūlymas', default='ne')
    price_include_selection = fields.Selection([('exc', 'be PVM'), ('inc', 'su PVM')], string='Kainos',
                                               default=default_price_include_selection)
    confirmed = fields.Boolean(string='Invoice was confirmed once by client')

    @api.multi
    def action_invoice_cancel(self):
        precision_id = self.sudo().env['decimal.precision'].search([('name', '=', 'Product Unit of Measure')], limit=1)
        if precision_id:
            old_precision = precision_id.digits
            precision_id.digits = 3
        else:
            old_precision = 0
        res = super(AccountInvoice, self).action_invoice_cancel()
        if precision_id:
            precision_id.digits = old_precision
        return res

    @api.multi
    def action_invoice_open(self):
        for rec in self:
            if not rec.move_name:
                rec.sudo().write({'date_invoice': datetime.utcnow()})
            if rec.sudo().imported_api and not rec.sudo().confirmed:
                rec.sudo().write({
                    'date_invoice': datetime.utcnow(),
                    'confirmed': True,
                })
        return super(AccountInvoice, self).action_invoice_open()

    @api.model
    def create(self, vals):
        if vals.get('imported_api') and vals.get('force_taxes'):
            vals.pop('force_taxes')
        return super(AccountInvoice, self).create(vals)

    @api.multi
    def write(self, vals):
        if any(self.sudo().mapped('imported_api')) and any([r in ['proforma', 'proforma2', 'draft'] for r in self.mapped('state')]) and vals.get('force_taxes'):
            vals.pop('force_taxes')
        force_taxes_write = 'force_taxes' in vals
        force_taxes = vals.get('force_taxes', False)
        if not self._context.get('recursion_prev', False) and not force_taxes:
            # In case someone edited lines on an imported_api invoice, poping force_taxes is not enough, we need to pop
            # tax_line_ids too, otherwise it will not be poped out later and try to write on record deleted by compute_taxes
            vals.pop('tax_line_ids', None)
            self.with_context(recursion_prev=True).compute_taxes()
        res = super(AccountInvoice, self).write(vals)
        if force_taxes_write and not force_taxes:
            self.with_context(recursion_prev=True).compute_taxes()
        return res


AccountInvoice()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    price_unit_wo_vat = fields.Monetary(string='Kaina be PVM', compute='_price_unit_wo_vat',
                                             currency_field='company_currency_id')

    @api.one
    @api.depends('quantity', 'price_subtotal')
    def _price_unit_wo_vat(self):
        if self.quantity:
            self.price_unit_wo_vat = self.price_subtotal / self.quantity


AccountInvoiceLine()
