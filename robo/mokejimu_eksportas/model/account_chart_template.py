# -*- coding: utf-8 -*-
from odoo import models, api


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    @api.multi
    def generate_account(self, tax_template_ref, acc_template_ref, code_digits, company):
        self.ensure_one()
        acc_template_ref = super(AccountChartTemplate, self).generate_account(
            tax_template_ref, acc_template_ref, code_digits, company)
        account_tmpl_obj = self.env['account.account.template']
        for account_template_id in acc_template_ref:
            account_template = account_tmpl_obj.browse(account_template_id)
            new_account = acc_template_ref[account_template_id]
            self.env['account.account'].browse(new_account).use_rounding = account_template.use_rounding
            self.env['account.account'].browse(
                new_account).cashflow_activity_id = account_template.cashflow_activity_id.id
        return acc_template_ref
