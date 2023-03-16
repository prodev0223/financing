# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class DynamicReportUserColumnSettings(models.Model):
    _name = 'dynamic.report.user.column.settings'
    _order = 'sequence,id'

    settings_id = fields.Many2one('dynamic.report.settings', string='Dynamic Report Settings', required=True,
                                  readonly=True, ondelete='cascade')
    column_id = fields.Many2one('dynamic.report.column', readonly=True, required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=1, index=True)
    shown = fields.Boolean('Column is shown', default=True)

    @api.multi
    @api.constrains('shown')
    def _check_at_least_single_column_is_shown(self):
        settings = self.mapped('settings_id')
        shown_columns = self.search([('settings_id', 'in', settings.ids), ('shown', '=', True)])
        for setting in settings:
            shown_columns_for_settings = shown_columns.filtered(lambda col: col.settings_id == setting)
            if not shown_columns_for_settings:
                raise exceptions.ValidationError(_('At least a single column must be shown for the report.'))

    @api.model
    def create_column_settings_for_missing_columns(self, settings):
        report_model = settings.report_model_id
        if not report_model:
            return
        existing_column_settings = self.search([('settings_id', '=', settings.id)])
        missing_columns = self.env['dynamic.report.column'].search([
            ('report_model_id', '=', report_model.id),
            ('id', 'not in', existing_column_settings.mapped('column_id').ids)
        ])
        for missing_column in missing_columns:
            self.create({
                'settings_id': settings.id,
                'column_id': missing_column.id,
                'shown': missing_column.shown_by_default
            })
