# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _get_default_asset_transfer_loss_account(self):
        return self.env['account.account'].search([('code', '=', '6400')], limit=1)

    def _get_default_asset_transfer_profit_account(self):
        return self.env['account.account'].search([('code', '=', '5400')], limit=1)

    account_asset_transfer_loss = fields.Many2one('account.account', string='Asset transfer loss account',
                                                  help='Ilgalaikio turto perleidimo nuostolis. Pvz. 6400',
                                                  default=_get_default_asset_transfer_loss_account)
    account_asset_transfer_profit = fields.Many2one('account.account', string='Asset transfer profit account',
                                                    help='Ilgalaikio turto perleidimo pelnas. Pvz. 5400',
                                                    default=_get_default_asset_transfer_profit_account)

    validate_assets_automatically = fields.Boolean(string='Validate assets automatically when confirming invoice',
                                                   compute='_compute_validate_assets_automatically',
                                                   inverse='_set_validate_assets_automatically')

    @api.multi
    def _compute_validate_assets_automatically(self):
        self.ensure_one()
        validate_assets = self.env['ir.config_parameter'].sudo().get_param('validate_assets_automatically') == 'True'
        self.validate_assets_automatically = validate_assets

    @api.multi
    def _set_validate_assets_automatically(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('validate_assets_automatically',
                                                         str(self.validate_assets_automatically))


ResCompany()
