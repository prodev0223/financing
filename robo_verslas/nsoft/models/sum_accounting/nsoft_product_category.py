# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
import itertools as it
STATIC_ACCOUNT_PREFIX = '2010'


class NsoftProductCategory(models.Model):
    _name = 'nsoft.product.category'

    # External ID's
    name = fields.Char(string='Pavadinimas', required=True)
    external_id = fields.Integer(string='Išorinis ID', required=True, inverse='_inverse_external_id')

    # Relational fields
    product_category_id = fields.Many2one('product.category', string='Sisteminė produkto kategorija')
    parent_product_id = fields.Many2one('product.product', string='Sisteminis produktas')
    forced_tax_id = fields.Many2one(
        'account.tax', string='Priverstinis kategorijos PVM',
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'sale')]"
    )

    # Other fields
    state = fields.Selection([('working', 'Veikianti'),
                              ('failed', 'Trūksta konfigūracijos (Produktas/Kategorija/Sąskaitos)')],
                             string='Būsena', track_visibility='onchange', compute='_compute_state', store=True)

    @api.one
    @api.depends('product_category_id', 'parent_product_id')
    def _compute_state(self):
        """Compute"""
        self.state = 'working' if self.product_category_id and self.parent_product_id and \
                     self.parent_product_id.product_tmpl_id.property_account_expense_id and \
                     self.parent_product_id.product_tmpl_id.property_account_prime_cost_id else 'failed'

    @api.multi
    def _inverse_external_id(self):
        """
        Inverse //
        Create expense account, product category and product template records
        based on fetched sum accounting category name and external_id
        :return: None
        """
        # Ref needed objects
        ProductTemplate = self.env['product.template'].sudo()
        AccountAccount = self.env['account.account'].sudo()
        ProductCategory = self.env['product.category'].sudo()

        # Ref needed records
        user_type_id = self.env.ref('account.data_account_type_current_assets').id
        account_5000_id = self.env.ref('l10n_lt.1_account_412').id
        account_6000_id = self.env.ref('l10n_lt.1_account_438').id

        for rec in self:
            product_template = ProductTemplate.search(
                [('default_code', '=', 'NSOFT/{}'.format(rec.external_id))])

            if not product_template:
                # Ensure that the loop is not endless
                counter = it.count()
                account_number = self.get_account_account_number()
                while AccountAccount.search_count([('code', '=', account_number)]):
                    account_number = self.get_account_account_number()
                    if next(counter) > 99:
                        # If this happens in any database, this part should be adjusted
                        # by adding pool of static prefixes or even making a new field
                        # that can be used to specify prefixes in nsoft settings.
                        # Error message is meant for developers.
                        raise exceptions.ValidationError(_('nSoft account sequence exhausted!'))

                expense_account = AccountAccount.create({
                    'name': 'nSoft Išlaidos / {}'.format(rec.name),
                    'code': account_number,
                    'reconcile': False,
                    'user_type_id': user_type_id,
                })
                category = ProductCategory.search([('name', '=', 'NSOFT/{}'.format(rec.name))])
                if not category:
                    category_vals = {
                        'name': 'NSOFT/{}'.format(rec.name),
                        'parent_id': False,
                        'property_cost_method': 'standard'
                    }
                    category = ProductCategory.create(category_vals)
                rec.product_category_id = category

                template_vals = {
                    'name': 'NSOFT / {}'.format(rec.name),
                    'default_code': 'NSOFT/{}'.format(rec.external_id),
                    'type': 'service',
                    'acc_product_type': 'service',
                    'categ_id': category.id,
                    'property_account_income_id': account_5000_id,
                    'property_account_prime_cost_id': account_6000_id,
                    'property_account_expense_id': expense_account.id
                }
                product_template = ProductTemplate.create(template_vals)
                if product_template:
                    rec.parent_product_id = product_template.product_variant_ids[0]
            else:
                rec.parent_product_id = product_template.product_variant_ids[0]
                rec.product_category_id = product_template.categ_id

    @api.model
    def get_account_account_number(self):
        """
        Get next available account code number in the system
        for nsoft.product.category expense account record
        :return: None
        """
        account_seq = self.env['ir.sequence'].next_by_code('NSOFT_CAT_SEQ')
        account_number = STATIC_ACCOUNT_PREFIX + str(account_seq)
        return account_number
