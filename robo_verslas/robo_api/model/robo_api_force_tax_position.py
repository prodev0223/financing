# -*- encoding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class RoboApiForceTaxPosition(models.Model):

    _name = 'robo.api.force.tax.position'

    name = fields.Char(string='Pavadinimas')
    country_id = fields.Many2one('res.country', string='Taikoma šaliai')
    country_group_id = fields.Many2one('res.country.group', string='Taikoma šalių grupei')
    not_country_id = fields.Many2one('res.country', string='Netaikoma šaliai')
    not_country_group_id = fields.Many2one('res.country.group', string='Netaikoma šalių grupei')
    force_tax_id = fields.Many2one('account.tax', string='Mokesčiai',
                                   domain=[('price_include', '=', True), ('type_tax_use', '=', 'sale')], required=True)
    force_tax_type = fields.Selection([('price_include', 'Su PVM'), ('price_exclude', 'Be PVM')],
                                      string='Mokesčių tipas', default='price_include', required=True)
    product_type = fields.Selection([('all', 'Visi'), ('product', 'Produktas'), ('service', 'Paslauga')],
                                    string='Produkto tipas', default='all', required=True)
    partner_type = fields.Selection([('all', 'Visi'), ('physical', 'Fizinis asmuo'), ('juridical', 'Juridinis asmuo')],
                                    string='Partnerio tipas', default='all', required=True)
    partner_vat_payer_type = fields.Selection([('all', 'Visi'), ('vat_payer', 'Moka PVM'),
                                               ('not_vat_payer', 'Nemoka PVM')],
                                              string='PVM mokėtojo tipas', default='all', required=True)
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

    @api.model
    def get_tax_of_position_applied(self, partner_id, invoice_date, product_type):
        """
        Get force tax applied to invoice
        :param partner_id: ID of a partner record
        :param invoice_date: date of invoice
        :param product_type: product type: product/service
        :return: tax of a position, if found, False otherwise
        """
        partner = self.env['res.partner'].browse(partner_id).exists()
        if not partner:
            return False

        partner_country_id = partner.country_id.id
        partner_type = 'juridical' if partner.is_company else 'physical'
        partner_vat_payer_type = 'vat_payer' if partner.vat and partner.vat.strip() else 'not_vat_payer'
        base_domain = [
            ('partner_type', 'in', [partner_type, 'all']),
            ('partner_vat_payer_type', 'in', [partner_vat_payer_type, 'all']),
            ('product_type', 'in', [product_type, 'all']),
            ('date_from', '<=', invoice_date),
            '|',
            ('date_to', '>=', invoice_date),
            ('date_to', '=', False),
        ]

        not_country_domain = [
            '|',
            ('not_country_id', '!=', partner_country_id),
            ('not_country_id', '=', False),
            '|',
            ('not_country_group_id.country_ids', '!=', partner_country_id),
            ('not_country_group_id', '=', False)
        ]

        # Priority #1: Search for a position that has country specified
        domain = base_domain + not_country_domain + [('country_id', '=', partner_country_id)]
        position = self.search(domain, limit=1)
        # Priority #2: Search for a position that has country group specified
        if not position:
            domain = base_domain + not_country_domain + [('country_group_id.country_ids', '=', partner_country_id)]
            position = self.search(domain, limit=1)
        # Priority #3: Search for a position that only has excluded countries
        if not position:
            extra_domain = [
                ('country_id', '=', False),
                ('country_group_id', '=', False),
                '&',
                '|',
                ('not_country_id', '!=', partner_country_id),
                ('not_country_id', '=', False),
                '|',
                ('not_country_group_id.country_ids', '!=', partner_country_id),
                ('not_country_group_id', '=', False)
            ]
            domain = base_domain + extra_domain
            position = self.search(domain, limit=1)

        return position.force_tax_id if position else False

