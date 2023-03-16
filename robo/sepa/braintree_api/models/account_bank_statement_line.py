# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    braintree_transaction_ids = fields.One2many(
        'braintree.transaction', 'bank_statement_line_id',
        string='Corresponding Braintree transaction',
    )

    braintree_disbursement_transaction_ids = fields.One2many(
        'braintree.transaction', 'disbursement_bank_statement_line_id',
        string='Corresponding Braintree disbursement transaction',
    )
