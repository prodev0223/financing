# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AssetProductionWizard(models.TransientModel):
    _name = 'asset.production.wizard'

    name = fields.Char(string='Asset name', required=True)
    date = fields.Date(string='Date', required=True)
    debit_account_id = fields.Many2one('account.account', string='Debit account', required=True,
                                       domain=[('is_view', '=', False)])
    credit_account_id = fields.Many2one('account.account', string='Credit account', required=True,
                                        domain=[('is_view', '=', False)])
    gross_value = fields.Float(string='Gross value', required=True)
    tax_ids = fields.Many2many('account.tax', string='Taxes',
                               domain="[('code','in',['PVM9','PVM30','PVM31','PVM25','PVM26','PVM27'])]", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(AssetProductionWizard, self).default_get(fields_list=fields_list)
        asset_id = self._context.get('asset_id', False)
        if asset_id:
            asset_id = self.env['account.asset.asset'].browse(asset_id)
            if 'name' in fields_list:
                res['name'] = _(u'Ilgalaikio turto pasigaminimas - ') + asset_id.name
            if 'date' in fields_list:
                res['date'] = asset_id.pirkimo_data if asset_id.pirkimo_data else asset_id.date
            if 'debit_account_id' in fields_list:
                res['debit_account_id'] = asset_id.category_id.account_asset_id.id
            if 'gross_value' in fields_list:
                res['gross_value'] = asset_id.value
            if 'tax_ids' in fields_list:
                tax_ids = self.env['account.tax'].search([('code', '=', 'PVM9'), ('type_tax_use', '=', 'sale')])
                tax_id = False
                for t_id in tax_ids:
                    if '35' in t_id.tag_ids.mapped('code'):
                        tax_id = t_id
                        break
                reverse_tax_id = self.env['account.tax'].search([('code', '=', 'A21'), ('type_tax_use', '=', 'sale')],
                                                                limit=1)
                tids = []
                if tax_id:
                    tids.append(tax_id.id)
                if reverse_tax_id:
                    tids.append(reverse_tax_id.id)
                tids = list(set(tids))
                res['tax_ids'] = tids
            return res
        else:
            return res

    @api.multi
    def confirm(self):
        asset_id = self._context.get('asset_id', False)
        if asset_id:
            invoice_lines = [(0, 0, {
                'name': self.name,
                'account_id': self.credit_account_id.id,
                'quantity': 1.0,
                'price_unit': self.gross_value,
                'invoice_line_tax_ids': [(6, 0, self.tax_ids.mapped('id'))],
            })]
            journal_id = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
            invoice_vals = {
                'partner_id': self.env.user.company_id.partner_id.id,
                'journal_id': journal_id.id if journal_id else False,
                'type': 'out_invoice',
                'invoice_line_ids': invoice_lines,
                'invoice_type': 'imt',
                'account_id': self.debit_account_id.id,
            }
            invoice_id = self.env['account.invoice'].create(invoice_vals)
            invoice_id.compute_taxes()
            self.env['account.asset.asset'].browse(asset_id).invoice_id = invoice_id.id
            return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.invoice',
                'res_id': invoice_id.id,
                'view_id': self.env.ref('robo.pajamos_form').id,
                'context': {'default_type': 'out_invoice', 'type': 'out_invoice', 'journal_type': 'sale'},
                'target': 'current',
            }


AssetProductionWizard()
