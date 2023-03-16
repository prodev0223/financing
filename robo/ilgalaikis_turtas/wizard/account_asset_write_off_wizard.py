# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, tools


class AccountAssetWriteOffWizard(models.TransientModel):
    _name = 'account.asset.write.off.wizard'

    def _default_account_asset_ids(self):
        return [(6, 0, self._context.get('account_asset_ids', False))]

    def _default_account_types_domain(self):
        allowed_ids = [self.env.ref('account.data_account_type_expenses').id]
        return [(6, 0, allowed_ids)]

    def _default_account_close(self):
        return self.env['account.account'].search([('code', 'like', '652')], limit=1)

    def _default_writeoff_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    account_close = fields.Many2one('account.account', string='Account to use for write-off', help='E.g. 6118',
                                    domain="[('deprecated','=',False), ('user_type_id', 'in', "
                                           "account_types_domain and account_types_domain[0][2])]", required=True, default=_default_account_close)
    account_asset_ids = fields.Many2many('account.asset.asset', required=True, default=_default_account_asset_ids)
    account_types_domain = fields.Many2many('account.account.type', default=_default_account_types_domain)
    writeoff_date = fields.Date(string='Nurašymo data', required=True, default=_default_writeoff_date)

    @api.onchange('account_asset_ids')
    def _onchange_account_asset_ids(self):
        dates = self.mapped('account_asset_ids.isvedimas_id.name')
        if len(dates) == 1:
            self.writeoff_date = dates[0]

    @api.multi
    def write_off(self):
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        for asset in self.account_asset_ids:
            if use_sudo and not self.env.user.has_group('base.group_system'):
                asset.message_post('Writing off asset')
                asset.sudo().write_off(self.account_close.id, self.writeoff_date)
            else:
                asset.write_off(self.account_close.id, self.writeoff_date)


AccountAssetWriteOffWizard()
