# -*- encoding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class RoboCompanySettingsApiForceTaxPosition(models.TransientModel):

    _name = 'robo.company.settings.api.force.tax.position'

    name = fields.Char(string='Pavadinimas')
    settings_id = fields.Many2one('robo.company.settings')
    position_id = fields.Many2one('robo.api.force.tax.position', ondelete='cascade')
    country_id = fields.Many2one('res.country', string='Taikoma šaliai', ondelete='cascade')
    country_group_id = fields.Many2one('res.country.group', string='Taikoma šalių grupei', ondelete='cascade')
    not_country_id = fields.Many2one('res.country', string='Netaikoma šaliai', ondelete='cascade')
    not_country_group_id = fields.Many2one('res.country.group', string='Netaikoma šalių grupei',
                                           ondelete='cascade')
    force_tax_id = fields.Many2one('account.tax', string='Mokesčiai',
                                   domain=[('price_include', '=', True), ('type_tax_use', '=', 'sale')],
                                   ondelete='cascade', required=True)
    force_tax_type = fields.Selection([('price_include', 'Su PVM'), ('price_exclude', 'Be PVM')],
                                      string='Mokesčių tipas', default='price_include', required=True)
    product_type = fields.Selection([('all', 'Visi'), ('product', 'Produktas'), ('service', 'Paslauga')],
                                    string='Produkto tipas', default='all', required=True)
    partner_type = fields.Selection([('all', 'Visi'), ('physical', 'Fizinis asmuo'), ('juridical', 'Juridinis asmuo')],
                                    string='Partnerio tipas', default='all', required=True)
    partner_vat_payer_type = fields.Selection([('all', 'Visi'), ('vat_payer', 'Moka PVM'),
                                               ('not_vat_payer', 'Nemoka PVM')], string='PVM mokėtojo tipas',
                                              default='all', required=True)
    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki')

    @api.onchange('force_tax_type')
    def _onchange_force_tax_type(self):
        """
        Reset the tax domain of force_tax_id based on
        forced tax type settings
        :return: JS readable domain (dict)
        """
        self.force_tax_id = None
        domain = [('price_include', '=', self.force_tax_type == 'price_include'), ('type_tax_use', '=', 'sale')]
        return {'domain': {'force_tax_id': domain}}

    @api.multi
    @api.constrains('country_id', 'country_group_id', 'not_country_id', 'not_country_group_id')
    def _check_country_constraints(self):
        for rec in self:
            if not rec.country_id and not rec.country_group_id and not rec.not_country_id and \
                    not rec.not_country_group_id:
                raise exceptions.UserError(_('Šalių apribojimai turi būti nustatyti.'))

