# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class CashflowActivity(models.Model):

    _name = 'cashflow.activity'

    code = fields.Char(string='Code', translate=True)
    name = fields.Char(string='Name', translate=True)


CashflowActivity()


class AccountAccount(models.Model):

    _inherit = 'account.account'

    cashflow_activity_id = fields.Many2one('cashflow.activity', string='Cashflow Activity')


AccountAccount()


class AccountAccountTemplate(models.Model):

    _inherit = 'account.account.template'

    cashflow_activity_id = fields.Many2one('cashflow.activity', string='Cashflow Activity')


AccountAccountTemplate()


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    cashflow_activity_id = fields.Many2one(
        'cashflow.activity', string='Cashflow Activity'
    )
    cashflow_balance = fields.Monetary(
        currency_field='company_currency_id',
        default=0.0, help="Technical field holding cashflow value"
    )

    @api.multi
    @api.depends('debit', 'credit', 'move_id.matched_percentage', 'move_id.journal_id')
    def _compute_cash_basis(self):
        """
        !COMPLETE OVERRIDE OF ADD-ONS METHOD!
        Additionally checks for extra journals when calculating cash basis
        """
        j_obj = self.env['account.journal']
        extra_journals = [
            self.env.user.company_id.salary_journal_id.id or j_obj.search([('code', '=', 'ATLY')], limit=1).id,
            self.env.user.company_id.vat_journal_id.id or j_obj.search([('code', '=', 'PVM')], limit=1).id,
        ]
        for move_line in self:
            # Get the matched factor
            matched_factor = 1
            if move_line.journal_id.type in ('sale', 'purchase') or move_line.journal_id.id in extra_journals:
                matched_factor = move_line.move_id.matched_percentage
            # Calculate debit, credit and balance basis
            move_line.debit_cash_basis = move_line.debit * matched_factor
            move_line.credit_cash_basis = move_line.credit * matched_factor
            move_line.balance_cash_basis = move_line.debit_cash_basis - move_line.credit_cash_basis
