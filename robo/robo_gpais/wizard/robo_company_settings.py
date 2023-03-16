# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    gpais_registras_alyva = fields.Integer(string='Alyvos registro ID')
    gpais_registras_pakuotes = fields.Integer(string='Pakuočių registro ID')
    gpais_registras_transportas = fields.Integer(string='Transporto priemonių registro ID')
    gpais_registras_elektra = fields.Integer(string='Elektros ir elektroninės įrangos registro ID')
    gpais_registras_baterijos = fields.Integer(string='Baterijų ir akumuliatorių registro ID')
    gpais_registras_gaminiai = fields.Integer(string='Apmokestinamųjų gaminių registro ID')
    gpais_registras_alyva_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_registras_pakuotes_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_registras_transportas_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_registras_elektra_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_registras_baterijos_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_registras_gaminiai_data = fields.Date(string='Pradėta tiekti rinkai nuo')
    gpais_default_veiklos_budas = fields.Many2one('gpais.klasifikacija', domain="[('code_class', '=', 'CL118')]",
                                                  string='GPAIS numatytasis veiklos būdas')
    gpais_testing = fields.Boolean(string='GPAIS testavimo aplinka')

    @api.model
    def default_get(self, field_list):
        if not self.env.user.is_manager():
            return {}
        res = super(RoboCompanySettings, self).default_get(field_list)
        res.update({
            'gpais_registras_alyva': self.env.user.sudo().company_id.gpais_registras_alyva,
            'gpais_registras_pakuotes': self.env.user.sudo().company_id.gpais_registras_pakuotes,
            'gpais_registras_transportas': self.env.user.sudo().company_id.gpais_registras_transportas,
            'gpais_registras_elektra': self.env.user.sudo().company_id.gpais_registras_elektra,
            'gpais_registras_baterijos': self.env.user.sudo().company_id.gpais_registras_baterijos,
            'gpais_registras_gaminiai': self.env.user.sudo().company_id.gpais_registras_gaminiai,
            'gpais_registras_alyva_data': self.env.user.sudo().company_id.gpais_registras_alyva_data,
            'gpais_registras_pakuotes_data': self.env.user.sudo().company_id.gpais_registras_pakuotes_data,
            'gpais_registras_transportas_data': self.env.user.sudo().company_id.gpais_registras_transportas_data,
            'gpais_registras_elektra_data': self.env.user.sudo().company_id.gpais_registras_elektra_data,
            'gpais_registras_baterijos_data': self.env.user.sudo().company_id.gpais_registras_baterijos_data,
            'gpais_registras_gaminiai_data': self.env.user.sudo().company_id.gpais_registras_gaminiai_data,
            'gpais_default_veiklos_budas': self.env.user.sudo().company_id.gpais_default_veiklos_budas.id,
            'gpais_testing': self.env.user.sudo().company_id.gpais_testing,
        })
        return res

    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
        res = super(RoboCompanySettings, self).set_company_info()
        company_id = self.sudo().company_id
        company_id.write({
            'gpais_registras_alyva': self.gpais_registras_alyva,
            'gpais_registras_pakuotes': self.gpais_registras_pakuotes,
            'gpais_registras_transportas': self.gpais_registras_transportas,
            'gpais_registras_elektra': self.gpais_registras_elektra,
            'gpais_registras_baterijos': self.gpais_registras_baterijos,
            'gpais_registras_gaminiai': self.gpais_registras_gaminiai,
            'gpais_registras_alyva_data': self.gpais_registras_alyva_data,
            'gpais_registras_pakuotes_data': self.gpais_registras_pakuotes_data,
            'gpais_registras_transportas_data': self.gpais_registras_transportas_data,
            'gpais_registras_elektra_data': self.gpais_registras_elektra_data,
            'gpais_registras_baterijos_data': self.gpais_registras_baterijos_data,
            'gpais_registras_gaminiai_data': self.gpais_registras_gaminiai_data,
            'gpais_default_veiklos_budas': self.gpais_default_veiklos_budas.id,
            'gpais_testing': self.gpais_testing,
        })
        return res
