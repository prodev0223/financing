# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    enable_neopay_integration = fields.Boolean(string='Enable Neopay integration')

    @api.model
    def _get_company_info_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_info_field_list()
        res.append('enable_neopay_integration')
        return res

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.sudo().env.user.company_id
        res['enable_neopay_integration'] = company.enable_neopay_integration
        return res
