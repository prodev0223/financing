# -*- coding: utf-8 -*-

from odoo import models, fields, api


class DynamicReportSettings(models.Model):
    _name = 'dynamic.report.settings'
    _inherits = {
        'dynamic.report.global.settings': 'settings_id',
    }

    @api.model
    def get_report_model_domain(self):
        dynamic_report_model = self.env.ref('account_dynamic_reports.model_dynamic_report', raise_if_not_found=False)
        if not dynamic_report_model:
            return [('id', 'in', [])]

        dynamic_report_models = self.env['ir.model'].search([
            ('transient', '=', True)
        ]).filtered(lambda model: dynamic_report_model in model.inherited_model_ids)
        return [('id', 'in', dynamic_report_models.ids)]

    report_model_id = fields.Many2one('ir.model', 'Report model', required=True, domain=get_report_model_domain)
    settings_id = fields.Many2one('dynamic.report.global.settings', 'Dynamic Report Settings', required=True,
                                  ondelete='cascade')
    column_setting_ids = fields.One2many('dynamic.report.user.column.settings', 'settings_id',
                                         string='Report column settings')

    @api.multi
    def get_shown_column_identifiers(self):
        self.ensure_one()
        self.env['dynamic.report.user.column.settings'].create_column_settings_for_missing_columns(self)
        return self.column_setting_ids.filtered(lambda col: col.shown).sorted(
            key=lambda col: col.sequence
        ).mapped('column_id.identifier')
