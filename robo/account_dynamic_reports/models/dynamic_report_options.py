# -*- coding: utf-8 -*-

from odoo import fields, models, api


class DynamicReportOptions(models.AbstractModel):
    _name = 'dynamic.report.options'

    @api.model
    def _default_report_language(self):
        user_lang = self.env.user.lang
        available_report_lanugages = dict(self._fields.get('report_language').selection)
        return user_lang if user_lang in available_report_lanugages else 'lt_LT'

    report_language = fields.Selection([
        ('lt_LT', 'Lithuanian'),
        ('en_US', 'English')
    ], string='Report language', default=_default_report_language, required=True)
