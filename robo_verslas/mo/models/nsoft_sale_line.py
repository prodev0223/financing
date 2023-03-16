# -*- coding: utf-8 -*-
from odoo import models, api, tools

STATIC_ZERO_RATE_VAT = 'PVM5'


class NsoftSaleLine(models.Model):
    _inherit = 'nsoft.sale.line'

    @api.multi
    @api.depends('vat_rate')
    def _compute_tax_id(self):
        """
        !! METHOD FULLY OVERRIDDEN - Original source - nsoft/nsoft_sale_line.py !!
        Compute tax_id for nsoft sale line record based on the vat rate
        """
        for rec in self:
            account_tax_forced = rec.nsoft_product_category_id.forced_tax_id
            tax_domain = [('type_tax_use', '=', 'sale'), ('price_include', '=', True)]
            if tools.float_is_zero(rec.vat_rate, precision_digits=2):
                account_tax = self.env['account.tax'].search(
                    [('code', '=', STATIC_ZERO_RATE_VAT)] + tax_domain, limit=1)
            else:
                account_tax = self.env['account.tax'].search([('amount', '=', rec.vat_rate)] + tax_domain, limit=1)
            if account_tax_forced and account_tax and not tools.float_compare(
                    account_tax_forced.amount, account_tax.amount, precision_digits=2):
                if account_tax_forced.type_tax_use != 'sale' or not account_tax_forced.price_include:
                    account_tax_forced = account_tax_forced.find_matching_tax_varying_settings(type_tax_use='sale')
                account_tax = account_tax_forced
            rec.tax_id = account_tax

    @api.multi
    def _set_cash_register_id(self):
        """Override of cash register setting, force static FP register to sales that do not have it"""
        super(NsoftSaleLine, self)._set_cash_register_id()
        # Search for default cash register, if it does not exist, return
        default_cash_register = self.env['nsoft.cash.register'].search(
            [('cash_register_number', '=', 'FP')], limit=1
        )
        if not default_cash_register:
            return
        # Write default cash register to the sales that do not have it
        self.filtered(lambda x: not x.cash_register_id and not x.cash_register_number).write({
            'cash_register_id': default_cash_register.id,
        })

