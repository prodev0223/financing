# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class AmazonProductCategory(models.Model):
    _name = 'amazon.sp.product.category'

    # Names / Codes
    name = fields.Char(string='Name', required=True)
    external_id = fields.Char(string='External ID', required=True)
    marketplace_code = fields.Char(string='Marketplace code', inverse='_set_marketplace')

    # Other fields
    category_type = fields.Selection(
        [('products', 'Products'), ('services', 'Services')], required=True,
        default='products', string='Category type', inverse='_set_category_type'
    )
    configured = fields.Boolean(string='Configured', compute='_compute_configured')
    activated = fields.Boolean(string='Activated', default=True)

    # Relational fields
    product_category_id = fields.Many2one('product.category', string='System product category')
    amazon_product_ids = fields.One2many('amazon.sp.product', 'amazon_category_id', string='Amazon products')
    marketplace_id = fields.Many2one('amazon.sp.marketplace', string='Marketplace')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('product_category_id', 'activated')
    def _compute_configured(self):
        """Determine whether Amazon product category is configured or not"""
        for rec in self:
            rec.state = rec.product_category_id and rec.activated

    @api.multi
    def _set_marketplace(self):
        """Assign related marketplace based on external code"""
        for rec in self.filtered(lambda x: x.marketplace_code):
            marketplace = self.env['amazon.sp.marketplace'].search([('code', '=', rec.marketplace_code)])
            rec.marketplace_id = marketplace

    @api.multi
    def _set_category_type(self):
        """
        Change the type of related product.category object and it's products
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
                    error = _('You cannot change the type of this category, products already have accounting entries.')
                    if self.env.user.has_group('base.group_system'):
                        error += _('Exception - {}').format(exc.args[0])
                    raise exceptions.UserError(error)

    @api.multi
    @api.constrains('external_id')
    def _check_external_id(self):
        """Ensure that product category external ID is unique"""
        for rec in self:
            if self.search_count([('external_id', '=', rec.external_id)]) > 1:
                raise exceptions.ValidationError(_('Product category external ID must be unique'))

    # Other methods ---------------------------------------------------------------------------------------------------

    @api.multi
    def create_system_category(self):
        """
        Create system product.category record using Amazon category data
        then proceed with Amazon product creation that belong to this category
        :return: None
        """
        ProductCategory = self.env['product.category'].sudo()
        for rec in self.filtered(lambda x: not x.product_category_id):
            # Search for the category and create it if it's not found
            category = ProductCategory.search([('amazon_sp_category_code', '=', rec.external_id)])
            if not category:
                category_vals = {
                    'name': rec.name, 'code': rec.external_id,
                    'parent_id': False, 'accounting_category_type': rec.category_type,
                }
                category = ProductCategory.create(category_vals)
                category.onchange_category_type()
            rec.product_category_id = category
            # Create all of the category products as system templates
            rec.amazon_product_ids.create_product_template_prep()

    @api.multi
    def button_create_system_category(self):
        """Button method that is used to create system category"""
        self.ensure_one()
        self.create_system_category()
