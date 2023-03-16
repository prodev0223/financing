# -*- encoding: utf-8 -*-
import logging
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    @api.multi
    def update_balance_from_revolut_legs(self):
        """
        Update statement balances using the revolut.api.transaction.legs associated with the statement
        """
        # Lastmile integration is mixing transactions from different revolut accounts so we don't want to use the
        # balance information from the transaction leg as it is usually related to the card account only
        # TODO: implement account balance checking from Revolut API
        for statement in self:
            statement.write({
                'balance_end_real': statement.balance_end,
            })


AccountBankStatement()
