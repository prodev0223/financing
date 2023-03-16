# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _


class AccountAssetMergeWizard(models.TransientModel):
    _name = 'account.asset.merge.wizard'

    @api.model
    def default_get(self, fields):
        res = super(AccountAssetMergeWizard, self).default_get(fields)
        asset_ids = self.env.context.get('account_asset_ids')
        if asset_ids:
            ordered_asset = self._get_ordered_asset(asset_ids)[-1]
            res.update({
                'asset_ids': asset_ids,
                'category_id': ordered_asset.category_id.id,
            })
        return res

    name = fields.Char(string='Name')
    asset_ids = fields.Many2many('account.asset.asset', string='Assets')
    category_id = fields.Many2one('account.asset.category', string='Asset category')
    date = fields.Date(string='Entry date')
    date_first_depreciation = fields.Date(string='First depreciation date')

    @api.model
    def _get_ordered_asset(self, asset_ids):
        return self.env['account.asset.asset'].browse(asset_ids).sorted(
            key=lambda p: (p.active, p.create_date),
            reverse=True,
        )

    def merge_assets(self):
        self.ensure_one()
        AccountAsset = self.env['account.asset.asset']

        if len(self.asset_ids) < 2:
            raise exceptions.UserError(_('No assets to merge'))

        value = sum(rec.value for rec in self.asset_ids)
        original_value = sum(rec.original_value for rec in self.asset_ids)
        category = self.category_id
        asset_values = {
            'name': self.name,
            'category_id': category.id,
            'date': self.date,
            'date_first_depreciation': self.date_first_depreciation,
            'value': value,
            'original_value': original_value,
            'quantity': 1.0,
            'original_quantity': 1.0,
            'salvage_value': 1.0,
            'account_analytic_id': category.account_analytic_id.id or False,
        }
        changed_values = AccountAsset.onchange_category_id_values(category.id)
        asset_values.update(changed_values['value'])
        asset = AccountAsset.create(asset_values)

        merged_asset_body = _('This asset was merged to asset {} {}').format(asset.id, asset.name)
        new_asset_body = _('''<span>This asset was created from these assets:\n</span>
                            <table border="2" width=100%%>
                                <tr>
                                    <td><b>ID</b></td>
                                    <td><b>Number</b></td>
                                    <td><b>Name</b></td>
                                </tr>''')
        for line in self.asset_ids:
            new_asset_body += '''<tr><td>{}</td><td>{}</td><td>{}</td></tr>'''.format(line.id, line.code or str(), line.name)
            line.write({
                'active': False
            })
            line.message_post(body=merged_asset_body)
        new_asset_body += '''</table>'''
        asset.message_post(body=new_asset_body)

        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.asset.asset',
            'res_id': asset.id,
            'view_id': self.env.ref('ilgalaikis_turtas.form_account_asset_asset_front').id,
        }
