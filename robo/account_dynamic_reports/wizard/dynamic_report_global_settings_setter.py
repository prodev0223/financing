# -*- coding: utf-8 -*-

from odoo import models, api, fields


class DynamicReportsGlobalSettingsSetter(models.TransientModel):
    _name = 'dynamic.report.global.settings.setter'

    @api.model
    def _get_global_dynamic_report_settings(self):
        return self.env['dynamic.report.global.settings'].get_global_dynamic_report_settings()

    settings_id = fields.Many2one('dynamic.report.global.settings', 'Settings',
                                  default=lambda self: self._get_global_dynamic_report_settings())
    user_id = fields.Many2one('res.users', related='settings_id.user_id', readonly=True)
    color_scheme = fields.Selection([('dark', 'Dark'), ('light', 'Light')], string='Color Scheme', required=True)

    @api.model
    def default_get(self, fields_to_get):
        res = super(DynamicReportsGlobalSettingsSetter, self).default_get(fields_to_get)
        # Get settings
        settings = res.get('settings_id')
        if settings:
            settings = self.env['dynamic.report.settings'].browse(settings).exists()
        if not settings:
            settings = self._get_global_dynamic_report_settings()
        if not settings:
            return res

        # Check which fields can be retrieved from settings
        settings_fields = settings.sudo().read()[0]
        fields_to_get_from_settings = [x for x in fields_to_get if (x not in res or not res.get(x)) and x in settings_fields]
        res.update({field: settings_fields.get(field) for field in fields_to_get_from_settings})

        return res

    @api.multi
    def save(self):
        self.ensure_one()
        if not self.settings_id:
            self.settings_id = self._get_global_dynamic_report_settings()
        fields_to_write_to_settings = {}

        # Update user report settings
        setting_fields = self.settings_id._fields
        field_list = [
            field for field in setting_fields if
            not setting_fields.get(field).automatic and
            not setting_fields.get(field).compute and
            field in self._fields
        ]
        for f in field_list:
            m = self[f]
            if m is None:
                val = self[f]
            elif callable(m):
                val = m()
            else:
                val = m
            if isinstance(self._fields.get(f), fields.Many2one):
                if not isinstance(val, int):
                    val = val.id
                if self.settings_id[f].id != val:
                    fields_to_write_to_settings[f] = val
            else:
                if self.settings_id[f] != val:
                    fields_to_write_to_settings[f] = val
        if fields_to_write_to_settings:
            self.settings_id.write(fields_to_write_to_settings)
