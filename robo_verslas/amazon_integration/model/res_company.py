# -*- coding: utf-8 -*-

from odoo import models, fields, api
from .. import amazon_tools as at


class ResCompany(models.Model):
    """Extend ResCompany to hold amazon API data"""
    _inherit = 'res.company'

    # Dates
    amazon_api_sync_date = fields.Datetime(string='Amazon API sinchronizavimo data')
    amazon_accounting_threshold_date = fields.Date(string='Apskaitos pradžios data')

    amazon_integration_configured = fields.Boolean(string='Integracija sukonfigūruota')
    include_amazon_commission_fees = fields.Boolean(string='Traukti komisinį mokestį į Amazon sąskaitas')
    include_amazon_tax = fields.Boolean(string='Traukti papildomai pateikiamus PVM mokesčius į Amazon sąskaitas')

    # Intervals
    amazon_creation_interval = fields.Selection(
        [('weekly', 'Savaitinis'), ('daily', 'Dieninis')], string='Sąskaitų kūrimo intervalas', default='weekly')

    # Shifted creation day selection values, because if you select 0'th option,
    # field becomes empty in the form view since 0 is false-able value
    amazon_creation_weekday = fields.Selection(
        [(1, 'Pirmadienis'), (2, 'Antradienis'), (3, 'Trečiadienis'),
         (4, 'Ketvirtadienis'), (5, 'Penktadienis'), (6, 'Šeštadienis')], string='Savaitės diena', default=5)

    # Integration type
    amazon_integration_type = fields.Selection(
        [('sum', 'Suminė'), ('quantitative', 'Kiekinė')], string='Integracijos tipas', default='quantitative',
        inverse='_set_amazon_integration_type'
    )

    @api.multi
    def _set_amazon_integration_type(self):
        """
        Modify default system product and category
        based on Amazon integration type.
        :return: None
        """
        sum_category = self.env.ref('l10n_lt.product_category_30')
        quant_category = self.env.ref('l10n_lt.product_category_2')

        product = self.env['product.product'].with_context(lang='lt_LT').search(
            [('name', '=', at.STATIC_SUM_SYSTEM_PRODUCT_NAME)])
        account_2040 = self.env.ref('l10n_lt.1_account_195').id
        account_6000 = self.env.ref('l10n_lt.1_account_438').id

        # Assign the values based on type
        for rec in self:
            if rec.amazon_integration_type == 'sum':
                sum_category.write({'property_account_expense_categ_id': account_2040})
                product.write({'acc_product_type': 'product', 'categ_id': sum_category.id})
            else:
                sum_category.write({'property_account_expense_categ_id': account_6000})
                product.write({'acc_product_type': 'service', 'categ_id': quant_category.id})


ResCompany()
