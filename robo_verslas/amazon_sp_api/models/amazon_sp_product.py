# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from .. import amazon_sp_api_tools as at


class AmazonSPProduct(models.Model):
    _name = 'amazon.sp.product'

    # External Identifiers
    asin_product_code = fields.Char(string='ASIN product code', inverse='_set_ext_product_code')
    ext_product_code = fields.Char(string='External product ID', inverse='_set_ext_product_code')
    product_name = fields.Char(string='Name', required=True)

    # Group info that comes with the product (Topmost level)
    product_group = fields.Char(string='Product group')
    product_group_type = fields.Char(string='Product type')

    spec_product = fields.Boolean(string='Special product', inverse='_set_spec_product')
    product_id = fields.Many2one('product.product', string='System product')
    amazon_category_id = fields.Many2one('amazon.sp.product.category', string='Amazon product category')
    configured = fields.Boolean(compute='_compute_configured')

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    @api.depends('product_id', 'asin_product_code', 'ext_product_code')
    def _compute_configured(self):
        """
        Computes product state - It's working when it has both codes and system product
        associated with it
        """
        for rec in self:
            rec.configured = rec.product_id and (rec.spec_product or rec.asin_product_code)

    @api.multi
    def _set_ext_product_code(self):
        """
        If product has ASIN, but does not have ext_product_code, search for order lines
        that have this ASIN, and fetch ext_product_code from them
        """
        AmazonSPOrderLine = self.env['amazon.sp.order.line']
        for rec in self.filtered(lambda x: x.asin_product_code and not x.ext_product_code):
            order_line = AmazonSPOrderLine.search([('asin_product_code', '=', rec.asin_product_code)])
            if order_line:
                rec.write({'ext_product_code': order_line.ext_product_code})

    @api.multi
    def _set_spec_product(self):
        """Finds or creates matching product.template record for special product"""
        # Get/initiate needed values
        ProductTemplate = self.env['product.template']
        configuration = self.env['amazon.sp.api.base'].get_configuration()
        sum_integration = configuration.integration_type == 'sum'
        product_category = self.env.ref('l10n_lt.product_category_30')

        for rec in self.filtered(lambda x: x.spec_product):
            # If integration type is 'Sum', fetch static product template
            if sum_integration and rec.ext_product_code == at.STATIC_SUM_PRODUCT_CODE:
                template = ProductTemplate.search(
                    [('name', '=', at.STATIC_SUM_SYSTEM_PRODUCT_NAME)], limit=1)
                if not template:
                    template = self.create_product_template(
                        category=product_category,
                        product_name=at.STATIC_SUM_SYSTEM_PRODUCT_NAME
                    )
            else:
                template = ProductTemplate.search([('default_code', '=', rec.ext_product_code)], limit=1)
            if template.product_variant_ids:
                rec.product_id = template.product_variant_ids[0].id

    @api.multi
    @api.constrains('asin_product_code')
    def _check_asin_product_code(self):
        """Ensure that ASIN product code is unique"""
        for rec in self.filtered(lambda x: x.asin_product_code):
            if self.search_count([('asin_product_code', '=', rec.asin_product_code)]) > 1:
                raise exceptions.ValidationError(_('ASIN product code must be unique!'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def create_product_template_prep(self):
        """Prepares product template record creation using Amazon product and category data"""
        for rec in self.filtered(lambda x: not x.product_id and x.amazon_category_id.product_category_id):
            product_template = self.create_product_template(
                category=rec.amazon_category_id.product_category_id,
                product_name='Amazon/{}'.format(rec.product_name),
                asin_code=rec.asin_product_code
            )
            if product_template:
                rec.product_id = product_template.product_variant_ids[0]

    @api.model
    def create_product_template(self, category, product_name, asin_code=None):
        """Creates product template record using Amazon data"""
        pr_type = 'service' if category.accounting_category_type == 'services' else 'product'
        template_vals = {
            'name': product_name,
            'default_code': asin_code,
            'type': pr_type,
            'purchase_ok': False,
            'acc_product_type': pr_type,
            'categ_id': category.id
        }
        return self.env['product.template'].create(template_vals)

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Product [%s]') % (x.asin_product_code or x.ext_product_code)) for x in self]
