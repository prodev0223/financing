# -*- encoding: utf-8 -*-
from odoo import models, api, tools


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.multi
    def post(self):
        """Override account move post method
        by calling cash-flow balance calculations"""
        res = super(AccountMove, self).post()
        self.calculate_move_cash_flow_balance()
        return res

    @api.multi
    def calculate_move_cash_flow_balance(self):
        """
        Calculates cashflow balance for each non-liquidity move line
        from current move. Liquidity line balance is summed and then
        distributed between the lines.
        :return: None
        """
        for rec in self:
            liquidity_balance = 0.0
            non_liquidity_lines = liquidity_lines = self.env['account.move.line']
            # Do everything in one loop session w/o filtered
            for line in rec.line_ids:
                if line.user_type_id.type == 'liquidity':
                    liquidity_balance += line.balance
                    liquidity_lines |= line
                else:
                    non_liquidity_lines |= line
            # Calculate the balance of other lines
            non_liquidity_balance = sum(non_liquidity_lines.mapped('balance')) * -1
            # If liquidity balance is not zero and other lines' balance is equal to it - apply the cash flow
            apply_cash_flow = not tools.float_is_zero(
                liquidity_balance, precision_digits=2) and not tools.float_compare(
                non_liquidity_balance, liquidity_balance, precision_digits=2,
            )
            # Check if there's any non-liquidity lines and whether balance is not zero
            if apply_cash_flow:
                # Calculate and write cashflow balance
                for line in non_liquidity_lines:
                    line.write({
                        'cashflow_balance': line.balance * -1,
                        'cashflow_activity_id': line.account_id.cashflow_activity_id.id,
                    })
            else:
                liquidity_lines |= non_liquidity_lines
            # Cash-flow balance is always zero for liquidity lines
            liquidity_lines.write({'cashflow_balance': 0.0})
