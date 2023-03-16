# -*- coding: utf-8 -*-
from __future__ import division
from odoo import api, fields, models, exceptions, _


class AccountAssetSellWizard(models.TransientModel):
    _name = 'account.asset.sell.wizard'
    _description = 'Account Asset Sell Wizard'

    def default_lines(self):
        asset_ids = self._context.get('active_ids')
        assets = self.env['account.asset.asset'].browse(asset_ids)
        lines = [(5,)]
        tax_id = self.env['account.tax'].search([('type_tax_use', '=', 'sale'),
                                                 ('code', '=', 'PVM1'),
                                                 ('price_include', '=', True)], limit=1).mapped('id')
        account_id = self.env['account.account'].search([('code', '=', '5400')], limit=1).id
        if not account_id:
            account_id = self.env['account.account'].search([], limit=1).id
        for asset in assets:
            depr_lines = asset.depreciation_line_ids.filtered(lambda l: l.move_check).sorted(lambda l: l.depreciation_date, reverse=True)
            ctx_date = depr_lines[0].depreciation_date if depr_lines else False
            asset = asset.with_context(date=ctx_date)
            salvage_unit_val = asset.salvage_value / asset.quantity  # P3:DivOK
            base_sale_unit_val = asset.residual_price_unit
            quant = asset.residual_quantity
            vals = {'asset_id': asset.id,
                    'credit_account_id': account_id,
                    'currency_id': self.env.user.company_id.currency_id,
                    'price': base_sale_unit_val * quant + salvage_unit_val * quant,
                    'unit_price': base_sale_unit_val + salvage_unit_val,
                    'quantity': quant,
                    'tax_ids': [(6, 0, tax_id)]
                    }
            lines.append((0, 0, vals))
        return lines

    partner_id = fields.Many2one('res.partner', string='Partneris', required=True, ondelete='cascade')
    wizard_line_ids = fields.One2many('account.asset.sell.wizard.line', 'account_asset_sell_wizard_id',
                                      string='Ilgalaikis turtas', default=default_lines)
    currency_id = fields.Many2one('res.currency', string='Valiuta', required=True)
    date = fields.Date(string='Data', required=True, default=fields.Date.today())

    @api.onchange('date')
    def _onchange_date(self):
        if self.date:
            ctx_date = self.date
            for line in self.wizard_line_ids:
                # P3:DivOK
                salvage_unit_val = line.asset_id.with_context(date=ctx_date).salvage_value / line.asset_id.with_context(date=ctx_date).quantity
                unit_price = line.asset_id.with_context(date=ctx_date).residual_price_unit + salvage_unit_val
                line.unit_price = unit_price

    @api.onchange('partner_id')
    def onchange_parter_id(self):
        if self.partner_id:
            self.currency_id = self.partner_id.currency_id.id
        else:
            self.currency_id = self.env.user.company_id.currency_id.id

    @api.multi
    def create_invoice(self):
        self.ensure_one()
        invoice_lines = []
        for wizard_line in self.wizard_line_ids:
            asset = wizard_line.asset_id
            if not asset:
                raise exceptions.UserError(_('Neparinkta ilgalaikio turto kortelė'))
            invoice_line = wizard_line._get_invoice_line_vals()
            invoice_lines.append((0, 0, invoice_line))

        taxes = self.mapped('wizard_line_ids.tax_ids')
        if taxes and len(set(taxes.mapped('price_include'))) > 1:
            raise exceptions.UserError(_('Arba visi mokesčiai turi būti su PVM arba be, negali būti ir taip ir taip.'))
        price_include_selection = 'inc' if taxes and any(tax.price_include for tax in taxes) else 'exc'

        journal_id = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        invoice_vals = {
            'partner_id': self.partner_id.id,
            'journal_id': journal_id.id if journal_id else False,
            'type': 'out_invoice',
            'invoice_line_ids': invoice_lines,
            'account_id': self.partner_id.property_account_receivable_id.id,
            'date_invoice': self.date,
            'operacijos_data': self.date,
            'price_include_selection': price_include_selection,
        }
        invoice_id = self.env['account.invoice'].create(invoice_vals)
        invoice_id.compute_taxes()

        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice',
            'res_id': invoice_id.id,
            'view_id': self.env.ref('robo.pajamos_form').id,
            'context': {'default_type': 'out_invoice', 'type': 'out_invoice', 'journal_type': 'sale',
                        'show_related_asset': True, },
            'target': 'current',
        }


AccountAssetSellWizard()
