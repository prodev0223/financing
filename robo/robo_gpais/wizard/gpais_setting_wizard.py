# -*- coding: utf-8 -*-
from odoo import api, fields, models


class GpaisSettingWizard(models.TransientModel):
    _name = 'gpais.setting.wizard'

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
    gpais_skip_misregistered_elements = fields.Boolean(string='Praleisti neregistruotus įrašus',
                                                      help='Pažymėjus bus praleisti registrų neatitinkantys įrašai')
    gpais_registration_lines_eei = fields.Many2many('gpais.registration.line.eei',
                                                    relation='rel_gpais_setting_lines_wizard_eei')
    gpais_registration_lines_battery = fields.Many2many('gpais.registration.line.battery',
                                                    relation='rel_gpais_setting_lines_wizard_bat')
    gpais_registration_lines_package = fields.Many2many('gpais.registration.line.package',
                                                    relation='rel_gpais_setting_lines_wizard_pak')
    gpais_registration_lines_oil = fields.Many2many('gpais.registration.line.oil',
                                                    relation='rel_gpais_setting_lines_wizard_oil')
    gpais_registration_lines_transport = fields.Many2many('gpais.registration.line.transport',
                                                    relation='rel_gpais_setting_lines_wizard_tra')
    gpais_registration_lines_goods = fields.Many2many('gpais.registration.line.goods',
                                                    relation='rel_gpais_setting_lines_wizard_gam')
    gpais_report_package_on_reception = fields.Boolean(string='Report packages as soon as received')
    company_id = fields.Many2one('res.company')

    @api.model
    def default_get(self, field_list):
        if not self.env.user.is_manager():
            return {}
        res = super(GpaisSettingWizard, self).default_get(field_list)
        company_id = self.env.user.sudo().company_id
        res.update({
            'company_id': company_id.id,
            'gpais_registras_alyva': company_id.gpais_registras_alyva,
            'gpais_registras_pakuotes': company_id.gpais_registras_pakuotes,
            'gpais_registras_transportas': company_id.gpais_registras_transportas,
            'gpais_registras_elektra': company_id.gpais_registras_elektra,
            'gpais_registras_baterijos': company_id.gpais_registras_baterijos,
            'gpais_registras_gaminiai': company_id.gpais_registras_gaminiai,
            'gpais_registras_alyva_data': company_id.gpais_registras_alyva_data,
            'gpais_registras_pakuotes_data': company_id.gpais_registras_pakuotes_data,
            'gpais_registras_transportas_data': company_id.gpais_registras_transportas_data,
            'gpais_registras_elektra_data': company_id.gpais_registras_elektra_data,
            'gpais_registras_baterijos_data': company_id.gpais_registras_baterijos_data,
            'gpais_registras_gaminiai_data': company_id.gpais_registras_gaminiai_data,
            'gpais_default_veiklos_budas': company_id.gpais_default_veiklos_budas.id,
            'gpais_testing': company_id.gpais_testing,
            'gpais_skip_misregistered_elements': company_id.gpais_skip_misregistered_elements,
            'gpais_report_package_on_reception': company_id.gpais_report_package_on_reception,
        })

        gpais_registration_lines_eei_vals = [(0, 0, values) for values in
                                             company_id.gpais_registration_lines.generate_wizard_line_vals_eei()]
        gpais_registration_lines_bat_vals = [(0, 0, values) for values in
                                             company_id.gpais_registration_lines.generate_wizard_line_vals_battery()]
        gpais_registration_lines_pak_vals = [(0, 0, values) for values in
                                             company_id.gpais_registration_lines.generate_wizard_line_vals_package()]

        res.update({
            'gpais_registration_lines_eei': [(5, 0, 0)] + gpais_registration_lines_eei_vals,
            'gpais_registration_lines_battery': [(5, 0, 0)]+ gpais_registration_lines_bat_vals,
            'gpais_registration_lines_package': [(5, 0, 0)]+ gpais_registration_lines_pak_vals,
        })
        return res

    @api.multi
    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
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
            'gpais_skip_misregistered_elements': self.gpais_skip_misregistered_elements,
            'gpais_report_package_on_reception': self.gpais_report_package_on_reception,
            'gpais_registration_lines': [(5, 0, 0)] + [(0, 0, values) for values in (
                self.gpais_registration_lines_eei.get_line_values() +
                self.gpais_registration_lines_battery.get_line_values() +
                self.gpais_registration_lines_package.get_line_values() +
                self.gpais_registration_lines_oil.get_line_values() +
                self.gpais_registration_lines_transport.get_line_values() +
                self.gpais_registration_lines_goods.get_line_values()
            )]
        })
        #TODO: do not erase unchanged lines to keep history of write dates

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'robo.company.settings',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('robo.company_settings_form').id,
            'target': 'main',
        }
