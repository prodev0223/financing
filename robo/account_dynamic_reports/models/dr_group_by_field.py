# -*- coding: utf-8 -*-

from odoo import models, fields


class DynamicReportGroupByField(models.Model):
    _name = 'dr.group.by.field'

    report_model_id = fields.Many2one('ir.model', string='Report model', required=True, ondelete='cascade')
    name = fields.Char(string='Name', required=True, translate=True)
    identifier = fields.Char(string='Identifier', required=True)  # Should match one of the identifiers of each data row
    applied_by_default = fields.Boolean(string='Field applied by default')
    forced = fields.Boolean(string='Field forced')
    requires_report_to_be_reloaded = fields.Boolean(string='Requires the report to be reloaded')