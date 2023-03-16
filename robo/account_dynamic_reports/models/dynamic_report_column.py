# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class DynamicReportColumn(models.Model):
    _name = 'dynamic.report.column'

    report_model_id = fields.Many2one('ir.model', string='Report model', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', help="Specifies the sequence in which the column is shown")
    name = fields.Char(string='Name', required=True, translate=True)
    identifier = fields.Char(string='Column identifier', required=True)
    shown_by_default = fields.Boolean(string='Column is shown by default')
    is_number = fields.Boolean(string='Column is number', help='If set - special formatting is applied in the reports')
    calculate_totals = fields.Boolean(string='Calculate column totals',
                                      help='If enabled - totals will be calculated in the report for the column')

    @api.constrains
    def _check_totals_are_calculated_only_if_column_is_number(self):
        if any(rec.calculate_totals and not rec.is_number for rec in self):
            raise exceptions.ValidationError(_('If totals are calculated for a column - the column must be a number'))

    @api.multi
    def get_column_data(self):
        fields_to_get = [x for x in self._fields if not self._fields[x].automatic]
        return self.read(fields_to_get)
