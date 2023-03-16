# -*- coding: utf-8 -*-
from odoo import models, fields, api
from six import iteritems


class ProductCategory(models.Model):
    _inherit = 'product.category'

    refund_income_account_id = fields.Many2one('account.account', string='Refund Income Account',
                                               help='E.g. 5092', sequence=100,
                                               )
    refund_expense_account_id = fields.Many2one('account.account', string='Refund Expense Account', sequence=100)
    product_cost_account_id = fields.Many2one('account.account', string='Returns Account',
                                              help='Parduotų prekių savikaina pvz. 6091')
    fuel = fields.Boolean(string='Kuras', default=False)
    accounting_category_type = fields.Selection(
        [('products', 'Produktai'),
         ('services', 'Paslaugos'),
         ('cost_adjustments', 'Savikainos korekcijos')], string='Kategorijos apskaitos tipas', default='services')

    @api.model
    def default_get(self, field_list):
        """
        Get default data for category
        :param field_list: current model field list
        :return: updated default field values
        """
        res = super(ProductCategory, self).default_get(field_list)
        if res.get('accounting_category_type'):
            default_data = self.get_default_category_data()
            defaults = default_data[res['accounting_category_type']]
            res.update(defaults)
        return res

    @api.onchange('accounting_category_type')
    def onchange_category_type(self):
        """
        Change accounts and other accounting-related fields of the category,
        based on category type
        :return: None
        """
        if self.accounting_category_type:
            default_data = self.get_default_category_data()
            # Set data (write does not work in onchange, doing it with setattr)
            defaults = default_data[self.accounting_category_type]
            for field, value in iteritems(defaults):
                setattr(self, field, value)

    @api.model
    def get_default_category_data(self):
        """
        Get default account and other category data based on category type
        :return: default category data
        """
        # Ref needed accounts
        account_209 = self.env.ref('l10n_lt.1_account_223').id
        account_509 = self.env.ref('l10n_lt.1_account_414').id
        account_609 = self.env.ref('l10n_lt.1_account_444').id
        account_2040 = self.env.ref('l10n_lt.1_account_195').id
        account_5000 = self.env.ref('l10n_lt.1_account_412').id
        account_5001 = self.env.ref('l10n_lt.1_account_413').id
        account_6312 = self.env.ref('l10n_lt.1_account_475').id
        account_6000 = self.env.ref('l10n_lt.1_account_438').id

        # Prepare data for each of accounting category types
        default_data = {
            'products': {
                'property_cost_method': 'real',
                'property_valuation': 'real_time',
                'property_account_income_categ_id': account_5000,
                'property_account_expense_categ_id': account_209,
                'refund_income_account_id': account_209,
                'refund_expense_account_id': account_509,
                'product_cost_account_id': account_609,
                'property_stock_account_input_categ_id': account_209,
                'property_stock_account_output_categ_id': account_6000,
                'property_stock_valuation_account_id': account_2040
            },
            'services': {
                'property_cost_method': 'standard',
                'property_valuation': 'manual_periodic',
                'property_account_income_categ_id': account_5001,
                'property_account_expense_categ_id': account_6312
            },
            'cost_adjustments': {
                'property_cost_method': 'standard',
                'property_valuation': 'manual_periodic',
                'property_account_income_categ_id': account_5001,
                'property_account_expense_categ_id': account_209
            }
        }
        return default_data
