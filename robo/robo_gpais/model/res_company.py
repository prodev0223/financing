# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    gpais_registras_alyva = fields.Integer(string='Alyvos registro ID',
                                           groups='robo_basic.group_robo_premium_manager')
    gpais_registras_pakuotes = fields.Integer(string='Pakuočių registro ID',
                                              groups='robo_basic.group_robo_premium_manager')
    gpais_registras_transportas = fields.Integer(string='Transporto priemonių registro ID',
                                                 groups='robo_basic.group_robo_premium_manager')
    gpais_registras_elektra = fields.Integer(string='Elektros ir elektroninės įrangos registro ID',
                                             groups='robo_basic.group_robo_premium_manager')
    gpais_registras_baterijos = fields.Integer(string='Baterijų ir akumuliatorių registro ID',
                                               groups='robo_basic.group_robo_premium_manager')
    gpais_registras_gaminiai = fields.Integer(string='Apmokestinamųjų gaminių registro ID',
                                              groups='robo_basic.group_robo_premium_manager')
    gpais_default_veiklos_budas = fields.Many2one('gpais.klasifikacija', domain="[('code_class', '=', 'CL118')]",
                                                  string='GPAIS numatytasis veiklos būdas', ondelete='set null',
                                                  groups='robo_basic.group_robo_premium_manager')
    gpais_registras_alyva_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                             groups='robo_basic.group_robo_premium_manager')
    gpais_registras_pakuotes_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                                groups='robo_basic.group_robo_premium_manager')
    gpais_registras_transportas_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                                   groups='robo_basic.group_robo_premium_manager')
    gpais_registras_elektra_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                               groups='robo_basic.group_robo_premium_manager')
    gpais_registras_baterijos_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                                 groups='robo_basic.group_robo_premium_manager')
    gpais_registras_gaminiai_data = fields.Date(string='Pradėta tiekti rinkai nuo',
                                                groups='robo_basic.group_robo_premium_manager')
    gpais_testing = fields.Boolean(string='GPAIS testavimo aplinka', groups='robo_basic.group_robo_premium_manager')
    gpais_registration_lines = fields.One2many('gpais.registration.line', 'company_id')
    gpais_skip_misregistered_elements = fields.Boolean(string='Praleisti neregistruotus įrašus', default=True,
                                                      help='Pažymėjus bus praleisti registrų neatitinkantys įrašai')
    gpais_report_package_on_reception = fields.Boolean(string='Report packages as soon as received')

    @api.constrains('gpais_report_package_on_reception', 'gpais_default_veiklos_budas')
    def _check_default_activity_type_when_report_on_arrival(self):
        for rec in self:
            if rec.gpais_report_package_on_reception and not rec.gpais_default_veiklos_budas:
                raise exceptions.UserError(_('You need to set a default activity type when reporting all packages on reception'))
