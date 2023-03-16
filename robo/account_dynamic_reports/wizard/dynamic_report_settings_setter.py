# -*- coding: utf-8 -*-

from odoo import models, api, fields


class DynamicReportsSettingsSetter(models.TransientModel):
    _name = 'dynamic.report.settings.setter'
    _inherits = {
        'dynamic.report.global.settings.setter': 'global_settings_setter_id'
    }

    @api.model
    def _get_user_settings(self):
        global_settings = self.env['dynamic.report.global.settings'].get_global_dynamic_report_settings()
        report_model = self._context.get('report_model')
        if report_model:
            return global_settings.get_report_settings(report_model)
        return False

    global_settings_setter_id = fields.Many2one('dynamic.report.global.settings.setter', required=True,
                                                ondelete='cascade')
    report_settings_id = fields.Many2one('dynamic.report.settings', 'Settings',
                                         default=lambda self: self._get_user_settings(), required=True,
                                         ondelete='cascade')
    column_setting_ids = fields.One2many('dynamic.report.user.column.settings', string='Report column settings',
                                         related='report_settings_id.column_setting_ids')

    @api.model
    def default_get(self, fields_get):
        res = super(DynamicReportsSettingsSetter, self).default_get(fields_get)
        # Get settings
        settings_id = res.get('report_settings_id')
        settings = None
        if settings_id:
            settings = self.env['dynamic.report.settings'].browse(settings_id).exists()
        if not settings:
            settings = self._get_user_settings()
        if not settings:
            return res

        if 'column_setting_ids' in fields_get:
            self.env['dynamic.report.user.column.settings'].create_column_settings_for_missing_columns(settings)
            res.update({'column_setting_ids': super(DynamicReportsSettingsSetter, self).default_get(['column_setting_ids'])})

        # Check which fields can be retrieved from settings
        settings_fields = settings.read()[0]
        fields_to_get_from_settings = [x for x in fields_get if (x not in res or not res.get(x)) and x in settings_fields]
        res.update({field: settings_fields.get(field) for field in fields_to_get_from_settings})

        return res

    @api.multi
    def save(self):
        self.ensure_one()
        self.global_settings_setter_id.save()
        if not self.report_settings_id:
            self.report_settings_id = self._get_user_settings()
        fields_to_write_to_settings = {}

        # Update user report settings
        setting_fields = self.report_settings_id._fields
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
                if self.report_settings_id[f].id != val:
                    fields_to_write_to_settings[f] = val
            else:
                if self.report_settings_id[f] != val:
                    fields_to_write_to_settings[f] = val
        if fields_to_write_to_settings:
            self.report_settings_id.write(fields_to_write_to_settings)
