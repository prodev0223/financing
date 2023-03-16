# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountVoucherLine(models.Model):
    _inherit = 'account.voucher.line'

    price_subtotal_signed = fields.Monetary(string='Amount Signed', store=True, readonly=True,
                                            compute='_compute_subtotal_signed')

    @api.one
    @api.depends('price_subtotal', 'voucher_id.state', 'currency_id')
    def _compute_subtotal_signed(self):
        voucher = self.voucher_id
        amount = voucher.currency_id.with_context({'date': voucher.date}).compute(self.price_subtotal,
                                                                                  voucher.company_id.currency_id)
        self.price_subtotal_signed = amount
