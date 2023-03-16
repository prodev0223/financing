# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    health_institiution_type_name = fields.Char(string='Sveikatos įstaigos steigėjo aprašymas')
    health_institiution_id_code = fields.Char(string='Sveikatos įstaigos ID kodas')
    allow_exclude_data_from_du_aspi_report = fields.Boolean(
        string='Allow excluding bonus data from DU ASPI reports',
        help='When this box is checked an additional box will appear on bonus EDoc where you can select if you want '
             'the bonuses created by the document to be included in DU ASPI report',)

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        if self.env.user.is_manager():
            company_id = self.sudo().env.user.company_id
            res['health_institiution_type_name'] = company_id.health_institiution_type_name
            res['health_institiution_id_code'] = company_id.health_institiution_id_code
            res['allow_exclude_data_from_du_aspi_report'] = company_id.allow_exclude_data_from_du_aspi_report
        return res

    @api.multi
    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
        self.ensure_one()
        company_id = self.sudo().company_id
        company_id.write({
            'health_institiution_type_name': self.health_institiution_type_name,
            'health_institiution_id_code': self.health_institiution_id_code,
            'allow_exclude_data_from_du_aspi_report': self.allow_exclude_data_from_du_aspi_report,
        })
        return super(CompanySettings, self).set_company_info()


CompanySettings()
