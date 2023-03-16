# -*- coding: utf-8 -*-
from odoo import models, api, fields, tools
from odoo.tools import float_compare


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    print_display_discount = fields.Boolean(string='Rodyti nuolaidas', default=True)


AccountInvoice()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    prevent_discount_change = fields.Boolean(compute='_compute_prevent_discount_change')
    discount_manilla = fields.Float(string='Nuolaida', compute='_compute_discount_manilla')

    @api.one
    def _compute_prevent_discount_change(self):
        if self.invoice_id.sale_ids:
            self.prevent_discount_change = True

    @api.one
    def _compute_discount_manilla(self):
        if self.invoice_id.sale_ids:
            list_price = self.product_id.product_tmpl_id.list_price * self.quantity
            discount = 0
            if not tools.float_is_zero(list_price, precision_digits=2) and float_compare(
                    self.quantity * list_price, self.print_price_subtotal, precision_digits=2):
                discount = tools.float_round(
                    (list_price - self.print_price_subtotal) / list_price * 100, precision_digits=2)
            self.discount_manilla = discount
        else:
            self.discount_manilla = self.discount


AccountInvoiceLine()
