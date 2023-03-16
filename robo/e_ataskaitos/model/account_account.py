# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class AccountAccount(models.Model):

    _inherit = 'account.account'

    saf_t_account_id = fields.Many2one('saf.t.account', string='SAF-T classifier account')

    @api.multi
    def write(self, vals):
        skip_locked_check = 'saf_t_account_id' in vals and len(vals) == 1
        return super(AccountAccount, self.with_context(skip_locked_check=skip_locked_check)).write(vals)
