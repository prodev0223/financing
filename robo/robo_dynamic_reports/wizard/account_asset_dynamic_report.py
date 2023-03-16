# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import _, models, fields, api, tools


class AccountAssetDynamicReport(models.TransientModel):
    _name = "account.asset.dynamic.report"
    _inherit = "dynamic.report"

    _dr_base_name = _('Account Asset List')
    _report_tag = 'dynamic.aa'

    date_range = fields.Selection(default='this_month')
    date_from = fields.Date(string="Period from")
    date_to = fields.Date(string="Period to")

    target_assets = fields.Selection(
        [
            ('all_assets', 'Ongoing and Depreciated'),
            ('ongoing_only', 'Ongoing Only'),
        ], string='Target Assets',
        default='all_assets', required=True,
        dynamic_report_front_filter=True
    )

    asset_department_ids = fields.Many2many(
        'account.asset.department',
        string='Asset departments',
        dynamic_report_front_filter=True
    )

    asset_category_ids = fields.Many2many(
        'account.asset.category',
        string='Asset categories',
        dynamic_report_front_filter=True
    )

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        date_from = self.date_from
        date_to = self.date_to
        assets = self.get_assets_based_on_wizard_values()
        if not assets:
            return list()

        purchase_dates = []
        if not date_from or not date_to:
            purchase_dates = assets.mapped('pirkimo_data')
        if not date_from:
            date_from = min(purchase_dates) if purchase_dates else False
        if not date_to:
            write_off_dates = assets.mapped('writeoff_date')
            close_dates = assets.mapped('date_close')
            depreciation_dates = assets.mapped('depreciation_line_ids.depreciation_date')
            date_to = max(write_off_dates + close_dates + depreciation_dates)
        if not date_from:
            date_from = date_to
        if not date_from:
            return list()
        assets = assets.with_context(date_from=date_from, date_to=date_to)
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        day_before_date_from = (date_from_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        def _total_depreciation_amount(asset):
            depreciation_lines = asset.depreciation_line_ids.filtered(
                lambda l: l.move_check and date_from <= l.depreciation_date <= date_to
            )
            return sum(depreciation_lines.mapped('amount'))

        currency_id = self.env.user.company_id.currency_id.id

        res = [{
            '__record_data__': {
                'record_model': 'account.asset.asset',
                'record_ids': [asset.id]
            },
            'code': {
                'value': asset.code
            },
            'name': {
                'value': asset.name
            },
            'purchase_date': {
                'value': asset.pirkimo_data
            },
            'residual_quantity_at_start_date': {
                'value': asset.with_context(date=date_from).residual_quantity
            },
            'residual_quantity_at_end_date': {
                'value': asset.with_context(date=date_to).residual_quantity
            },
            'original_value': {
                'value': asset.original_value,
                'currency_id': currency_id,
            },
            'salvage_value': {
                'value': asset.salvage_value,
                'currency_id': currency_id,
            },
            'current_value': {
                'value': asset.current_value,
                'currency_id': currency_id,
            },
            'value_at_start_date': {
                'value': asset.with_context(date=day_before_date_from).value_at_date,
                'currency_id': currency_id,
            },
            'revaluation_amount': {
                'value': asset.with_context(date_from=date_from).change_between_dates,
                'currency_id': currency_id,
            },
            'write_off_amount': {
                'value': asset.write_off_between_dates,
                'currency_id': currency_id,
            },
            'depreciation_amount': {
                'value': _total_depreciation_amount(asset),
                'currency_id': currency_id,
            },
            'value_at_end_date': {
                'value': asset.with_context(date=date_to).value_at_date,
                'currency_id': currency_id,
            },
            'asset_department_id': {
                'value': asset.asset_department_id.id,
                'display_value': asset.asset_department_id.name
            },
            'category_id': {
                'value': asset.category_id.id,
                'display_value': asset.category_id.name,
            },
        } for asset in assets]
        return res

    @api.multi
    def get_assets_based_on_wizard_values(self):
        """
        Gets the assets based on wizard values
        @return: account.asset.asset to show on report
        """
        self.ensure_one()

        asset_states = ['open', 'close'] if self.target_assets == 'all_assets' else ['open']

        asset_domain = [
            ('active', '=', True),
            '|',
            ('state', 'in', asset_states),
            '&',
            ('state', '=', 'close'),
            ('sale_line_ids', '!=', False)
        ]

        asset_depreciation_line_domain = [
            ('move_check', '=', True),
            ('asset_id.active', '=', True),
            '|',
            ('asset_id.state', 'in', asset_states),
            '&',
            ('asset_id.state', '=', 'close'),
            ('asset_id.sale_line_ids', '!=', False)
        ]

        if self.date_to:
            asset_domain += ['|', ('pirkimo_data', '<=', self.date_to), ('date', '<=', self.date_to)]
            asset_depreciation_line_domain.append(('depreciation_date', '<=', self.date_to))

        if self.date_from:
            asset_domain += [
                '|',
                ('date', '>=', self.date_from),
                '|',
                ('date_close', '>=', self.date_from),
                ('date_close', '=', False)
            ]
            asset_depreciation_line_domain.append(('depreciation_date', '>=', self.date_from))

        if self.asset_department_ids:
            asset_domain.append(('asset_department_id', 'in', self.asset_department_ids.ids))
            asset_depreciation_line_domain.append(('asset_id.asset_department_id', 'in', self.asset_department_ids.ids))

        if self.asset_category_ids:
            asset_domain.append(('category_id', 'in', self.asset_category_ids.ids))
            asset_depreciation_line_domain.append(('asset_id.category_id', 'in', self.asset_category_ids.ids))

        assets = self.env['account.asset.asset'].search(asset_domain)
        assets |= self.env['account.asset.depreciation.line'].search(asset_depreciation_line_domain).mapped('asset_id')

        return assets

    @api.multi
    def get_pdf_footer(self):
        self.ensure_one()
        return self.env['ir.qweb'].with_context(lang=self.determine_language_code()).render(
            'robo_dynamic_reports.AccountAssetDynamicReportPDFFooter', {
                'accountant': self.env.user.company_id.findir.name
            }
        )
