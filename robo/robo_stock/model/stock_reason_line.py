# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockReasonLine(models.Model):

    _inherit = 'stock.reason.line'

    @api.model
    def _default_account_id(self):
        """Returns default account ID"""
        return self.env.ref('l10n_lt.account_account_8').id

    account_id = fields.Many2one(
        'account.account', default=_default_account_id
    )
    representation_split = fields.Boolean(string='Representation write-off')
    representation_non_deductible_account_id = fields.Many2one(
        'account.account', compute='_compute_representation_accounts',
        string='Non-deductible representation account'
    )
    representation_deductible_account_id = fields.Many2one(
        'account.account', compute='_compute_representation_accounts',
        string='Deductible representation account'
    )
    deductible_vat = fields.Boolean(string='Deductible VAT')
    create_invoice = fields.Boolean(string='Creates invoice')
    robo_front = fields.Boolean(string='Show record to user')

    @api.multi
    @api.depends('representation_split')
    def _compute_representation_accounts(self):
        """Compute representation accounts for stock reason line if representation split is set"""

        AccountAccount = self.env['account.account']
        # Get the deductible account
        deductible_account = AccountAccount.search([('code', '=', '6312021')])
        if not deductible_account:
            deductible_account = AccountAccount.search(
                [('name', '=', 'Reprezentacinės sąnaudos 50% (atskaitoma)')]
            )
        # Get non-deductible account
        non_deductible_account = AccountAccount.search([('code', '=', '6312022')])
        if not non_deductible_account:
            non_deductible_account = AccountAccount.search(
                [('name', '=', 'Reprezentacinės sąnaudos 50% (neatskaitoma)')])

        for rec in self.filtered('representation_split'):
            rec.representation_deductible_account_id = deductible_account
            rec.representation_non_deductible_account_id = non_deductible_account
