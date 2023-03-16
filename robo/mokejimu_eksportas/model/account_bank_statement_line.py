# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class AccountBankStatementLine(models.Model):

    _inherit = 'account.bank.statement.line'

    name = fields.Char(help='Laukelis Naudojamas kaip mokėjimo paskirtis')
    is_international = fields.Boolean(compute='_compute_is_international')
    invoice_id = fields.Many2one('account.invoice')

    @api.multi
    @api.depends('bank_account_id', 'bank_account_id.acc_number', 'amount')
    def _compute_is_international(self):
        """
        Compute //
        Determine whether front bank statement line is international transaction
        based on the IBAN number
        :return: None
        """
        for rec in self.filtered(
                lambda x: x.bank_account_id.acc_number and x.statement_id.journal_id.bank_acc_number):
            # Get both sender and receiver accounts
            sender_account = rec.statement_id.journal_id.bank_acc_number
            receiver_account = rec.bank_account_id.acc_number
            international = sender_account[:2] != receiver_account[:2]
            # Ensure that the amount is outgoing before setting the value
            if tools.float_compare(rec.amount, 0.0, precision_digits=2) < 0 and international:
                rec.is_international = True
