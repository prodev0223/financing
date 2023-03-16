# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    operation_act_creation = fields.Selection([('manual', 'Rankinis'),
                                               ('auto', 'Automatinis')], default='manual',
                                              string='Eksploatacijos aktų sudarymas')

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        res['operation_act_creation'] = self.env.user.sudo().company_id.operation_act_creation
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.append('operation_act_creation')
        return res
