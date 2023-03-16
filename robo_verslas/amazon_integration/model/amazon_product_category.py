# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class AmazonProductCategory(models.Model):
    _name = 'amazon.product.category'

    # Names / Codes
    name = fields.Char(string='Pavadinimas', required=True)
    external_id = fields.Char(string='Išorinis identifikatorius', required=True)
    group_from_product = fields.Char(string='Grupė iš produkto')
    marketplace_code = fields.Char(string='Parduotuvės kodas', inverse='_set_marketplace')

    # Other fields
    category_type = fields.Selection(
        [('products', 'Produktai'), ('services', 'Paslaugos')],
        required=True, default='products', string='Kategorijos tipas', inverse='_set_category_type')
    state = fields.Selection([('working', 'Veikianti'),
                              ('warning', 'Reikia įgalinti')],
                             string='Būsena', compute='_compute_state')
    activated = fields.Boolean(string='Aktyvuota', default=True)

    # Relational fields
    product_category_id = fields.Many2one('product.category', string='Sisteminė produkto kategorija')
    amazon_product_ids = fields.One2many('amazon.product', 'amazon_category_id', string='Amazon produktai')
    marketplace_id = fields.Many2one('amazon.marketplace', string='Prekiavietė')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('product_category_id', 'activated')
    def _compute_state(self):
        """
        Compute //
        Determine marketplace state
        :return: None
        """
        for rec in self:
            rec.state = 'working' if rec.product_category_id and rec.activated else 'warning'

    @api.multi
    def _set_marketplace(self):
        """
        Inverse //
        Create or assign a marketplace based on external code
        :return: None
        """
        for rec in self.filtered(lambda x: x.marketplace_code):
            marketplace = self.env['amazon.marketplace'].search([('marketplace_code', '=', rec.marketplace_code)])
            rec.marketplace_id = marketplace

    @api.multi
    def _set_category_type(self):
        """
        Change the type of related product.category object and it's products, if it fails
        throw an exception
        :return: None
        """
        for rec in self.filtered(lambda x: x.product_category_id and x.category_type):
            if rec.product_category_id.accounting_category_type != rec.category_type:
                try:
                    pr_type = 'service' if rec.category_type == 'services' else 'product'
                    rec.product_category_id.accounting_category_type = rec.category_type
                    rec.product_category_id.onchange_category_type()
                    rec.product_category_id.product_ids.write({'acc_product_type': pr_type, 'type': pr_type})
                except Exception as exc:
                    error = _('Nebegalima pakeisti kategorijos tipo - susiję produktai jau turi sukurtų įrašų.')
                    if self.env.user.has_group('base.group_system'):
                        error += _('Klaidos pranešimas - {}').format(exc.args[0])
                    raise exceptions.UserError(error)

    # Other methods ---------------------------------------------------------------------------------------------------

    @api.multi
    def create_system_category(self):
        """
        Create system product.category record using amazon.product.category data
        then proceed with amazon.product creation that belong to this category
        :return: None
        """
        for rec in self.filtered(lambda x: not x.product_category_id):
            category_id = self.env['product.category'].search([('code', '=', rec.external_id)])
            if not category_id:
                category_vals = {
                    'name': rec.name,
                    'code': rec.external_id,
                    'parent_id': False,
                    'accounting_category_type': rec.category_type
                }
                category_id = self.sudo().env['product.category'].create(category_vals)
                category_id.onchange_category_type()
            rec.product_category_id = category_id
            rec.amazon_product_ids.create_system_product()


AmazonProductCategory()
