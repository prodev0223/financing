# -*- coding: utf-8 -*-
from odoo import models, fields, api
from six import iteritems


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    refund_income_account_id = fields.Many2one('account.account', string='Refund Income Account',
                                               help='E.g. 5092', sequence=100,
                                               )
    refund_expense_account_id = fields.Many2one('account.account', string='Refund Expense Account', sequence=100)
    product_cost_account_id = fields.Many2one('account.account', string='Returns Account',
                                              help='Parduotų prekių savikaina pvz. 6091')
    track_service = fields.Selection(default='manual')

    @api.onchange('type', 'landed_cost_ok')
    def onchange_type(self):
        """
        Return specific domain to product category field
        if products type or landed cost settings are changed
        :return: JS readable domain (dict)
        """
        # Default domain copied from stock extend
        domain = [('id', '!=', 1), '|', ('ultimate_id', '=', False), ('ultimate_id.id', '!=', 1)]

        if self.landed_cost_ok:
            domain += [('accounting_category_type', '=', 'cost_adjustments')]
        elif self.type == 'service':
            domain += [('accounting_category_type', '=', 'services')]
        else:
            domain += [('accounting_category_type', '=', 'products')]
        return {'domain': {'categ_id': domain}}

    @api.onchange('type')
    def _onchange_type(self):
        self.track_service = 'manual'

    @api.multi
    def _get_product_accounts(self):
        """ we look through parent categories as well """
        acc_type_categ_name_mapping = {'income': 'property_account_income_categ_id',
                                       'expense': 'property_account_expense_categ_id',
                                       'stock_input': 'property_stock_account_input_categ_id',
                                       'stock_output': 'property_stock_account_output_categ_id',
                                       'stock_valuation': 'property_stock_valuation_account_id',
                                       }
        res = super(ProductTemplate, self)._get_product_accounts()
        for acc_type, categ_field in iteritems(acc_type_categ_name_mapping):
            if not res.get(acc_type):
                categ = self.categ_id
                while categ:
                    if categ[categ_field]:
                        res[acc_type] = categ[categ_field]
                        break
                    else:
                        categ = categ.parent_id
        return res
