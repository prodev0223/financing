# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountInvoiceDistributedPaymentLine(models.Model):
    _order = 'date'
    _name = 'account.invoice.distributed.payment.line'

    invoice_id = fields.Many2one('account.invoice', string='Invoice', ondelete="cascade", required=True,
                                 lt_string='Sąskaita')
    date = fields.Date(string='Mokėjimo data', required=True, lt_string='Mokėjimo data')
    currency_id = fields.Many2one(string='Valiuta', related='invoice_id.currency_id')
    amount = fields.Monetary(string='Suma')
