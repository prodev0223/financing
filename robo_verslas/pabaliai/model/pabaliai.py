# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    destination_account_id = fields.Many2one('account.account', compute='_compute_destination_account_id',
                                             readonly=True)

    @api.one
    @api.depends('invoice_ids', 'payment_type', 'partner_type', 'partner_id', 'force_destination_account_id')
    def _compute_destination_account_id(self):
        super(AccountPayment, self)._compute_destination_account_id()
        if self.advance_payment:
            self.destination_account_id = self.env['account.account'].search([('code', '=', '4484')]).id
        if self.force_destination_account_id:
            self.destination_account_id = self.force_destination_account_id.id


AccountPayment()
