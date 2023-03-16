# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    module_invoice_approval_workflow = fields.Boolean(string='Enable invoice approval',
                                                      groups='robo_basic.group_robo_premium_accountant')

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.append('module_invoice_approval_workflow')
        return res

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.sudo().env.user.company_id
        if self.env.user.is_accountant():
            res['module_invoice_approval_workflow'] = company.module_invoice_approval_workflow
        return res
