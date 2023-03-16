# -*- encoding: utf-8 -*-
from odoo import models, fields


class AccountInvoiceDistributedPaymentLineCreate(models.TransientModel):

    _name = 'account.invoice.distributed.payment.line.create'

    _order = 'date'

    wizard_id = fields.Many2one('account.invoice.distributed.payment.line.wizard', ondelete="cascade", required=True)
    date = fields.Date(string='Data', required=True)
    currency_id = fields.Many2one('res.currency')
    amount = fields.Monetary(string='Suma')
    correct = fields.Boolean(string='Fiksuoti', default=False)
