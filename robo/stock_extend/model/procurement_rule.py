# -*- coding: utf-8 -*-

from odoo import models, api, fields, _


class ProcurementRule(models.Model):
    _inherit = 'procurement.rule'

    mts_rule_id = fields.Many2one('procurement.rule', string='MTS Rule')
    mto_rule_id = fields.Many2one('procurement.rule', string='MTO Rule')

    @api.model
    def _get_action(self):
        """Add split_procurement option to the action field defined in add-ons"""
        res = super(ProcurementRule, self)._get_action()
        res.extend([('split_procurement', _('Choose between MTS and MTO'))])
        return res


ProcurementRule()
