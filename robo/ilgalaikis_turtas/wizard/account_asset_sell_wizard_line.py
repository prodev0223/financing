# -*- coding: utf-8 -*-
from __future__ import division
from odoo import fields, models, api, _, exceptions


class AccountAssetSellWizardLine(models.TransientModel):
    _name = 'account.asset.sell.wizard.line'
    _description = 'Account Asset Sell Wizard Line'

    account_asset_sell_wizard_id = fields.Many2one('account.asset.sell.wizard', string='Asset Sell Wizard',
                                                   ondelete='cascade')
    asset_id = fields.Many2one('account.asset.asset', string='Ilgalaikis turtas', ondelete='cascade', readonly=True, required=True)
    currency_id = fields.Many2one('res.currency', string='Valiuta', related='account_asset_sell_wizard_id.currency_id', readonly=True)
    product_id = fields.Many2one('product.product', string='Produktas')
    unit_price = fields.Monetary(string='Pardavimo Vieneto Kaina', required=True)
    quantity = fields.Float(string='Kiekis', required=True, default=1.0)
    price = fields.Monetary(string='Pardavimo kaina', required=True)
    credit_account_id = fields.Many2one('account.account', string='Pajamų/sąnaudų sąskaita')  # , required=True)
    tax_ids = fields.Many2many('account.tax', string='Taxes',
                               domain="[('type_tax_use','=','sale')]")

    @api.onchange('unit_price')
    def _onchange_unit_price(self):
        self.price = self.unit_price * self.quantity

    @api.onchange('price')
    def _onchange_price(self):
        try:
            self.unit_price = self.price / self.quantity  # P3:DivOK
        except ZeroDivisionError:
            self.unit_price = 0.0

    @api.onchange('quantity')
    def _onchange_quantity(self):
        self.price = self.unit_price * self.quantity

    @api.multi
    def _get_invoice_line_vals(self):
        self.ensure_one()
        asset_acc = self.asset_id.category_id.account_asset_id.id
        if not asset_acc:
            raise exceptions.UserError(_('Ilgalaikio turto kategorijoje nenustatyta ilgalaikio turto sąskaita'))
        return {
            'product_id': self.product_id.id,
            'name': self.asset_id.name,
            'account_id': asset_acc,
            'quantity': self.quantity,
            'price_unit': self.unit_price,
            'invoice_line_tax_ids': [(6, 0, self.tax_ids.mapped('id'))],
            'asset_id': self.asset_id.id,
        }


AccountAssetSellWizardLine()
