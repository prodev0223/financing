# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    license_number = fields.Char(string='Kompanijos licencijos numeris')

    @api.model
    def default_get(self, field_list):
        """Default get license from res company"""
        res = super(CompanySettings, self).default_get(field_list)
        res['license_number'] = self.sudo().env.user.company_id.license_number
        return res

    @api.multi
    def set_company_info(self):
        """Set license number in the company"""
        self.ensure_one()
        res = super(CompanySettings, self).set_company_info()
        self.env.user.company_id.sudo().write({'license_number': self.license_number})
        return res
