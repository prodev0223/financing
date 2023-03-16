# -*- coding: utf-8 -*-
from odoo import models, api


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    @api.multi
    def generate_fiscal_position(self, tax_template_ref, acc_template_ref, company):
        """ This method generate Fiscal Position, Fiscal Position Accounts and Fiscal Position Taxes from templates.

            :param chart_temp_id: Chart Template Id.
            :param taxes_ids: Taxes templates reference for generating account.fiscal.position.tax.
            :param acc_template_ref: Account templates reference for generating account.fiscal.position.account.
            :param company_id: company_id selected from wizard.multi.charts.accounts.
            :returns: True
        """
        self.ensure_one()
        positions = self.env['account.fiscal.position.template'].search([('chart_template_id', '=', self.id)])
        for position in positions:
            new_fp = self.create_record_with_xmlid(company, position, 'account.fiscal.position',
                                                   {'company_id': company.id, 'name': position.name,
                                                    'note': position.note,
                                                    'not_country_id': position.not_country_id.id,
                                                    'not_country_group_id': position.not_country_group_id.id,
                                                    'auto_apply': position.auto_apply,
                                                    'vat_required': position.vat_required})
            for tax in position.tax_ids:
                self.create_record_with_xmlid(company, tax, 'account.fiscal.position.tax', {
                    'tax_src_id': tax_template_ref[tax.tax_src_id.id],
                    'tax_dest_id': tax.tax_dest_id and tax_template_ref[tax.tax_dest_id.id] or False,
                    'position_id': new_fp,
                    'product_type': tax.product_type,
                })
            for acc in position.account_ids:
                self.create_record_with_xmlid(company, acc, 'account.fiscal.position.account', {
                    'account_src_id': acc_template_ref[acc.account_src_id.id],
                    'account_dest_id': acc_template_ref[acc.account_dest_id.id],
                    'position_id': new_fp
                })
        return True

    def _load_template(self, company, code_digits=None, transfer_account_id=None, account_ref=None, taxes_ref=None):
        account_ref, taxes_ref = super(AccountChartTemplate, self)._load_template(company, code_digits=code_digits,
            transfer_account_id=transfer_account_id, account_ref=account_ref, taxes_ref=taxes_ref)
        account_templates = self.env['account.account.template'].browse(account_ref.keys())
        for acc_templ in account_templates:
            if acc_templ.structured_code:
                acc_id = account_ref[acc_templ.id]
                acc = self.env['account.account'].browse(acc_id)
                acc.structured_code = acc_templ.structured_code
        return account_ref, taxes_ref
