# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class DynamicReportGlobalSettings(models.Model):
    _name = 'dynamic.report.global.settings'
    _description = 'User settings for dynamic reports'
    _sql_constraints = [('unique_user', 'unique(user_id)', _('There can only be one dynamic report settings per user'))]

    user_id = fields.Many2one('res.users', string='User', required=True)
    color_scheme = fields.Selection([('dark', 'Dark'), ('light', 'Light')], string='Color Scheme', default='light',
                                    required=True)
    custom_report_setting_ids = fields.One2many('dynamic.report.settings', 'settings_id', 'Custom report settings')

    @api.model
    def get_global_dynamic_report_settings(self):
        user = self.env.user
        return self.search([('user_id', '=', user.id)], limit=1) or self.create({'user_id': user.id})

    @api.multi
    def get_report_settings(self, report_model_name):
        self.ensure_one()
        report_model = self.env['ir.model'].sudo().search([('model', '=', report_model_name)], limit=1)
        if not report_model:
            return
        settings_for_report = self.custom_report_setting_ids.filtered(
            lambda settings: settings.report_model_id == report_model
        )
        settings_for_report = settings_for_report and settings_for_report[0]
        if not settings_for_report:
            settings_for_report = self.env['dynamic.report.settings'].create({
                'report_model_id': report_model.id,
                'settings_id': self.id
            })
        return settings_for_report
