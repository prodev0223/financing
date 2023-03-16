# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountAssetRevaluationHistory(models.Model):
    _name = 'account.asset.revaluation.history'

    _order = 'date desc'

    name = fields.Char(string='Reason', required=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    date = fields.Date(string='Revaluation date', required=True)
    method_number = fields.Integer(string='Number of Depereciations', required=True)
    old_value = fields.Float(string='Previous Value', required=True)
    new_value = fields.Float(string='New Value', required=True)
    value_difference = fields.Float(string='Value difference', compute='_value_difference', store=True)
    method_period = fields.Integer(string='Number of Months in a period', required=True)

    @api.multi
    @api.depends('new_value', 'old_value')
    def _value_difference(self):
        for rec in self:
            rec.value_difference = rec.new_value - rec.old_value


AccountAssetRevaluationHistory()
