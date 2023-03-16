# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, exceptions, _, tools
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    def _account_asset_id(self):
        if self._context.get('asset_being_sold_id'):
            return self.self._context['asset_being_sold_id']

    asset_id = fields.Many2one('account.asset.asset', string='Related Asset', default=_account_asset_id,
                               help='This the asset being sold. If it is nonempty, accounting entries will be different',
                               domain="[('written_off_or_sold', '=', False)]", copy=False)

    state = fields.Selection(string='Sąskaitos būsena', related='invoice_id.state', readonly=True)
    date_invoice = fields.Date(string='Sąskaitos data', related='invoice_id.date_invoice', readonly=True)
    used_in_calculations = fields.Boolean(string='Naudojama ilgalaikio turto skaičiavimuose', compute='_compute_used_in_calculations')
    revaluation_change = fields.Float(
        string='Perkainavimo kainos pokytis',
        help='Kaip pasikeitė perkainavimo vertės po šio pardavimo',
        compute='_compute_value_changes')
    depreciation_change = fields.Float(
        string='Kainos pokytis',
        help='Kaip pasikeitė vertės po šio pardavimo',
        compute='_compute_value_changes')

    @api.one
    def _compute_used_in_calculations(self):
        self.used_in_calculations = self.invoice_id.state in ['open', 'paid']

    @api.one
    def _compute_value_changes(self):
        if self.asset_id:
            depreciation_data = self.asset_id.current_depreciation_values(date=self.date_invoice)
            depreciation_left_at_sale_date = depreciation_data.get('depreciation_left', 0.0)
            revaluation_left_at_sale_date = depreciation_data.get('revaluation_left', 0.0)
            quantity_at_sale_date = self.asset_id.with_context(date=self.date_invoice).residual_quantity
            if tools.float_is_zero(quantity_at_sale_date, precision_digits=2):
                self.revaluation_change = 0.0
                self.depreciation_change = 0.0
                return

            depreciation_left_per_unit = revaluation_left_per_unit = 0
            if not tools.float_is_zero(quantity_at_sale_date, precision_digits=2):
                depreciation_left_per_unit = depreciation_left_at_sale_date / quantity_at_sale_date  # P3:DivOK
                revaluation_left_per_unit = revaluation_left_at_sale_date / quantity_at_sale_date  # P3:DivOK

            self.revaluation_change = -(revaluation_left_per_unit * self.quantity)
            self.depreciation_change = -(depreciation_left_per_unit * self.quantity)

    @api.one
    @api.depends('asset_category_id', 'invoice_id.date_invoice')
    def _get_asset_date(self):
        self.asset_mrr = 0
        self.asset_start_date = False
        self.asset_end_date = False
        cat = self.asset_category_id
        if cat:
            months = cat.method_number * cat.method_period
            if self.invoice_id.type in ['out_invoice', 'out_refund']:
                self.asset_mrr = self.price_subtotal_signed / months  # P3:DivOK
            if self.invoice_id.date_invoice:
                start_date = datetime.strptime(self.invoice_id.date_invoice,
                                               tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1, day=2)
                end_date = (start_date + relativedelta(months=months))
                self.asset_start_date = start_date.strftime(DF)
                self.asset_end_date = end_date.strftime(DF)

    @api.onchange('asset_category_id')
    def onchange_asset_category_id(self):

        if not self.product_id and not self.asset_category_id:
            if self.invoice_id.type in ('in_invoice', 'in_refund'):
                self.account_id = self.env['account.account'].search([('code', '=', '6001')], limit=1).id
            else:
                self.account_id = self.env['account.account'].search([('code', '=', '5001')], limit=1).id

        elif not self.asset_category_id:
            self.account_id = self.get_invoice_line_account(self.invoice_id.type, self.product_id,
                                                            self.invoice_id.fiscal_position_id,
                                                            self.invoice_id.company_id).id
        else:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.one
    def asset_create(self):
        material_asset_category_prefix = '12'
        if self.asset_category_id and self.invoice_id.type in ['in_invoice']:
            subtotal_value = self.currency_id.with_context(date=self.invoice_id.date_invoice).compute(
                self.price_subtotal, self.company_id.currency_id)
            salvage_coef = 1.0 if self.asset_category_id.method_number > 0 else 0.0
            date = datetime.strptime(self.invoice_id.operacijos_data, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date:
                date += relativedelta(months=1, day=1)
                date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                date = self.asset_start_date or self.invoice_id.date_invoice

            temp_qty = 0
            # Create a separate record for each material asset unit
            qty = 1 if self.asset_category_id.name[:2] == material_asset_category_prefix else self.quantity
            validate_assets = self.env.user.sudo().company_id.validate_assets_automatically
            while temp_qty < self.quantity:
                temp_qty += qty
                salvage_value = salvage_coef * qty
                value = subtotal_value / self.quantity * qty  # P3:DivOK
                vals = {
                    'name': self.name,
                    # 'code': self.invoice_id.number or False,
                    'category_id': self.asset_category_id.id,
                    'salvage_value': salvage_value,
                    'value': value,
                    'original_value': value,
                    'quantity': qty,
                    'original_quantity': qty,
                    'partner_id': self.invoice_id.partner_id.id,
                    'company_id': self.invoice_id.company_id.id,
                    'date': date,
                    'date_first_depreciation': date,
                    'invoice_id': self.invoice_id.id,
                    'pirkimo_data': self.invoice_id.date_invoice,
                    'account_analytic_id': self.asset_category_id.account_analytic_id.id or self.account_analytic_id.id
                }
                changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
                vals.update(changed_vals['value'])
                asset = self.env['account.asset.asset'].create(vals)
                if validate_assets:
                    asset.validate()
        return True


AccountInvoiceLine()
