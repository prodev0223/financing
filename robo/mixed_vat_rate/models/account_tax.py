# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.multi
    def get_account(self, refund=False):
        self.ensure_one()
        return refund and self.refund_account_id or self.account_id
