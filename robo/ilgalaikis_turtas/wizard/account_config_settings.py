# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    account_asset_transfer_loss = fields.Many2one('account.account', string='Asset transfer loss account',
                                                  related='company_id.account_asset_transfer_loss',
                                                  help='Ilgalaikio turto perleidimo nuostolis. Pvz. 621')
    account_asset_transfer_profit = fields.Many2one('account.account', string='Asset transfer profit account',
                                                    related='company_id.account_asset_transfer_profit',
                                                    help='Ilgalaikio turto perleidimo pelnas. Pvz. 521')


AccountConfigSettings()
