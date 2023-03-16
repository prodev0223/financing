# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from .. import amazon_tools as at


class AmazonProduct(models.Model):
    _name = 'amazon.product'

    # External ID's
    asin_product_code = fields.Char(string='ASIN Identifikatorius', inverse='_set_ext_product_code')
    ext_product_code = fields.Char(string='Užsakymo produkto ID', inverse='_set_ext_product_code')

    product_name = fields.Char(string='Pavadinimas', required=True)
    brand = fields.Char(string='Firma')
    model = fields.Char(string='Modelis')
    product_group = fields.Char(string='Produkto grupė')

    spec_product = fields.Boolean(string='Specialus produktas', inverse='_set_spec_product')
    product_id = fields.Many2one('product.product', string='Sisteminis produktas')
    amazon_category_id = fields.Many2one('amazon.product.category', string='Amazon produktų kategorija')
    state = fields.Selection([('working', 'Veikiantis'),
                              ('warning', 'Reikia aktyvuoti')],
                             string='Būsena', compute='_compute_state')

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    @api.depends('product_id', 'asin_product_code', 'ext_product_code')
    def _compute_state(self):
        """
        Compute //
        Compute product state -- It's working when it has both codes and system product
        associated with it
        :return: None
        """
        for rec in self:
            if rec.product_id and (rec.spec_product or (rec.asin_product_code and rec.ext_product_code)):
                rec.state = 'working'
            else:
                rec.state = 'warning'

    @api.multi
    def _set_ext_product_code(self):
        """
        Inverse //
        If product has ASIN, but does not have ext_product_code, search for order lines
        that have this ASIN, and fetch ext_product_code from them
        :return: None
        """
        for rec in self.filtered(lambda x: x.asin_product_code and not x.ext_product_code):
            order_line = self.env['amazon.order.line'].search([('asin_product_code', '=', rec.asin_product_code)])
            if order_line:
                rec.write({'ext_product_code': order_line.ext_product_code})

    @api.multi
    def _set_spec_product(self):
        """
        Inverse //
        Find matching product.template record for special product
        :return: None
        """
        sum_integration = self.sudo().env.user.company_id.amazon_integration_type == 'sum'
        for rec in self.filtered(lambda x: x.spec_product):

            # If integration type is 'Sum', fetch static product template
            if sum_integration and rec.ext_product_code == at.STATIC_SUM_PRINCIPAL_PRODUCT_CODE:
                template = self.env['product.template'].search(
                    [('name', '=', at.STATIC_SUM_SYSTEM_PRODUCT_NAME)], limit=1)
                if not template:
                    product_category = self.env.ref('l10n_lt.product_category_30')
                    template = self.create_system_product_non_bound(
                        category=product_category,
                        product_name=at.STATIC_SUM_SYSTEM_PRODUCT_NAME
                    )
            else:
                template = self.env['product.template'].search(
                    [('default_code', '=', rec.ext_product_code)], limit=1)
            if template.product_variant_ids:
                rec.product_id = template.product_variant_ids[0].id

    @api.multi
    @api.constrains('ext_product_code')
    def _check_ext_product_code(self):
        """
        Constraints //
        Amazon ext_product_code must be unique and it must be present
        :return: None
        """
        for rec in self:
            if not rec.ext_product_code:
                raise exceptions.ValidationError(_('Produktas privalo turėti išorinį kodą!'))
            if self.search_count(
                    [('ext_product_code', '=', rec.ext_product_code), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Produkto išorinis kodas turi būti unikalus!'))

    @api.multi
    @api.constrains('asin_product_code')
    def _check_asin_product_code(self):
        """
        Constraints //
        Amazon asin_product_code must be unique
        :return: None
        """
        for rec in self.filtered(lambda x: x.asin_product_code):
            if self.search_count(
                    [('asin_product_code', '=', rec.asin_product_code), ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Produkto ASIN kodas turi būti unikalus!'))

    @api.multi
    def recompute_fields(self):
        """
        Recompute and Re-inverse relevant fields
        :return: None
        """
        self._set_spec_product()
        self._set_ext_product_code()

    # Other methods ---------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Produktas %s') % x.ext_product_code) for x in self]

    @api.multi
    def create_system_product(self):
        """
        Create product.template record using
        amazon.product and amazon.product.category data
        :return: None
        """
        for rec in self.filtered(lambda x: not x.product_id and x.amazon_category_id.product_category_id):
            product_template = self.create_system_product_non_bound(
                category=rec.amazon_category_id.product_category_id,
                product_name='Amazon/{}'.format(rec.product_name),
                asin_code=rec.asin_product_code
            )
            if product_template:
                rec.product_id = product_template.product_variant_ids[0]

    @api.model
    def create_system_product_non_bound(self, category, product_name, asin_code=None):
        """
        Create system product based on Amazon product data.
        Method is not bound to the model.
        :return: product.template record
        """
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


AmazonProduct()
