# -*- encoding: utf-8 -*-
from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    statement_line_id = fields.Many2one(
        'account.bank.statement.line', index=True, readonly=True,
        string='Banko išrašo eilutė sudengta su šiuo įrašu', copy=False,
    )

    @api.multi
    def post(self):
        """
        Auto confirm related bank statement if all of
        it's lines have related account moves and if
        it's calculated amount differences are zero.
        :return: result of parent method
        """
        # Execute super of the post
        res = super(AccountMove, self).post()
        for rec in self.filtered('statement_line_id'):
            statement = rec.statement_line_id.statement_id
            if not statement.currency_id.is_zero(statement.difference):
                continue
            if all(x.journal_entry_ids.mapped('line_ids') for x in statement.line_ids):
                statement.check_confirm_bank()
        return res
