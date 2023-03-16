# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountTaxTemplate(models.Model):
    _inherit = 'account.tax.template'

    def default_group(self):
        return self.env.ref('account.tax_group_taxes')

    child_tax_ids = fields.Many2many('account.tax.template', 'account_template_children_mapping', 'parent_id',
                                     'child_id',
                                     string='Children taxes', domain="[('type_tax_use','=',type_tax_use)]")
    tax_group_id = fields.Many2one('account.tax.group', default=default_group, readonly=True)
    code = fields.Char(string='Code', required=True)
    # description = fields.Char(translate=True)
    # long_description = fields.Char(string='Description', translate=True)
    show_description = fields.Boolean(string='Show description on Invoices', default=False)

    def _get_tax_vals(self, company):
        vals = super(AccountTaxTemplate, self)._get_tax_vals(company)
        vals['code'] = self.code
        vals['show_description'] = self.show_description
        vals['tax_group_id'] = self.tax_group_id.id
        # vals['long_description'] = self.long_description
        return vals
