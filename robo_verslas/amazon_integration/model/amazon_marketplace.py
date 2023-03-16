# -*- coding: utf-8 -*-

from odoo import models, fields, exceptions, api, _
from .. import amazon_tools as at


class AmazonMarketplace(models.Model):
    """
    Model that holds information about failed/imported amazon XML tasks
    """
    _name = 'amazon.marketplace'

    @api.model
    def _default_taxes(self):
        """
        Get default taxes for products/services of the marketplace
        :return: account.tax record
        """
        return self.env['account.tax'].search(
            [('code', '=', 'Ne PVM'), ('price_include', '=', True)], limit=1)

    # Name / Code
    name = fields.Char(string='Prekiavietės pavadinimas', inverse='_set_name')
    marketplace_code = fields.Char(
        string='Prekiavietės kodas', readonly=True, inverse='_set_marketplace_code')

    # Other fields
    state = fields.Selection([('configured', 'Sukonfigūruota'),
                              ('warning', 'Nesukonfigūruota')],
                             string='Būsena', compute='_compute_state')
    activated = fields.Boolean(string='Aktyvuota')

    # Relational fields
    partner_id = fields.Many2one('res.partner', string='Susijęs partneris')
    country_id = fields.Many2one(
        'res.country', string='Prekiavėtės šalis', inverse='_set_country_id',
        domain="[('code', 'in', {})]".format(at.MARKETPLACE_COUNTRIES)
    )
    amazon_product_category_ids = fields.One2many(
        'amazon.product.category', 'marketplace_id', string='Prekiavietės kategorijos')
    product_tax_id = fields.Many2one(
        'account.tax', string='Mokestis produktams', default=_default_taxes,
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'sale')]"
    )
    service_tax_id = fields.Many2one(
        'account.tax', string='Mokestis paslaugoms', default=_default_taxes,
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'sale')]"
    )

    @api.multi
    @api.depends('partner_id', 'country_id', 'activated')
    def _compute_state(self):
        """
        Compute //
        Determine marketplace state (it must have partner, country and be activated)
        :return: None
        """
        for rec in self:
            rec.state = 'configured' if rec.partner_id and rec.country_id and rec.activated else 'warning'

    @api.multi
    def _set_country_id(self):
        """
        Inverse //
        Set marketplace code based on the country code
        (Used when creating from the form view)
        :return: None
        """
        for rec in self.filtered(lambda x: x.country_id and not x.marketplace_code):
            marketplace_code = at.MARKETPLACE_ID_MAPPING.get(rec.country_id.code)
            if marketplace_code:
                rec.marketplace_code = marketplace_code
            else:
                raise exceptions.UserError(
                    _('Negalima sukonfigūruoti Amazon prekiavietės pasirinktoje šalyje %s!') % rec.country_id.code)

    @api.multi
    def _set_marketplace_code(self):
        """
        Inverse //
        Set marketplace code based on the country code
        (Used when creating from the code)
        :return: None
        """
        for rec in self.filtered(lambda x: x.marketplace_code):
            country_code = at.REVERSE_MARKETPLACE_ID_MAPPING.get(rec.marketplace_code)
            country = self.env['res.country'].search([('code', '=', country_code)], limit=1)
            if not country:
                raise exceptions.UserError(_('Nerasta Amazon prekiavėtės šalis su kodu %s!') % country_code)
            rec.country_id = country

    @api.multi
    def _set_name(self):
        """
        Inverse //
        Create res.partner record based on marketplace name and country
        :return: None
        """
        for rec in self:
            partner_name = 'Marketplace {}'.format(rec.name)
            partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
            if not partner:
                partner_vals = {
                    'name': partner_name,
                    'kodas': partner_name,
                    'is_company': True,
                }
                partner = self.env['res.partner'].create(partner_vals)
            rec.partner_id = partner

    @api.multi
    @api.constrains('marketplace_code')
    def _check_marketplace_code(self):
        """
        Constraints //
        Ensure that every shop has unique marketplace code
        :return: None
        """
        for rec in self:
            if self.search_count([('id', '!=', rec.id), ('marketplace_code', '=', rec.marketplace_code)]):
                raise exceptions.UserError(_('Negalima turėti dviejų prekiaviečių su tuo pačiu kodu!'))


AmazonMarketplace()
