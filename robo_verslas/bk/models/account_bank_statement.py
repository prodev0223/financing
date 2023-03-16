# -*- encoding: utf-8 -*-
from odoo import api, models


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    @api.model
    def _get_allowed_file_type_for_normalization(self):
        res = super(AccountBankStatement, self)._get_allowed_file_type_for_normalization()
        if not res:
            res = []
        res.append('braintree_bk')
        return res
