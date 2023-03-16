# -*- encoding: utf-8 -*-
from odoo import models, fields, api, _


class ResCompany(models.Model):

    _inherit = 'res.company'

    def _get_default_cash_advance_account_id(self):
        acc = self.env['account.account'].search([('code', '=', '24450')], limit=1)
        return acc.id if acc else False

    cash_advance_account_id = fields.Many2one('account.account', string='Cash Advance Account',
                                              default=_get_default_cash_advance_account_id)


ResCompany()


class AccountConfigSettings(models.TransientModel):

    _inherit = 'account.config.settings'

    cash_advance_account_id = fields.Many2one('account.account', string='Cash Advance Account',
                                              related='company_id.cash_advance_account_id', required=True)

AccountConfigSettings()
