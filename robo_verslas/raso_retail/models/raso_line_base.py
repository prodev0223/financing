# -*- coding: utf-8 -*-

from odoo import models, api, tools, _


# Some products have forced taxes that
# cannot be calculated from the amounts
PRODUCT_TO_FORCED_TAX_MAPPING = {
    '1100000000000': 'Ne PVM'
}


class RasoLineBase(models.AbstractModel):
    """
    Abstract model that holds methods shared by raso.sales and raso.invoices.line
    MAY BE EXPANDED IN THE FUTURE...
    """
    _name = 'raso.line.base'

    @api.multi
    @api.depends('amount', 'vat_sum', 'line_type')
    def _compute_tax_id(self):
        """
        Compute //
        Find account.tax record for the raso sale line, based on
        forced tax code, or percentage that is calculated from
        other sale amounts
        :return: None
        """
        for rec in self:
            account_tax, force_taxes = rec.find_related_account_tax()
            rec.tax_id = account_tax
            rec.force_taxes = force_taxes

    @api.multi
    @api.depends('amount_man', 'vat_sum_man', 'has_man')
    def _compute_man_tax_id(self):
        """
        Compute //
        Find account.tax record for the raso sale line, based on
        forced tax code, or percentage that is calculated from
        other sale amounts
        :return: None
        """
        for rec in self:
            account_tax, force_taxes = rec.find_related_account_tax(manual_taxes=True)
            rec.man_tax_id = account_tax
            rec.force_taxes = force_taxes

    @api.multi
    def get_related_sales(self):
        self.ensure_one()
        return self.env['raso.sales']

    @api.multi
    def find_manual_tax_based_on_related_sales(self):
        self.ensure_one()

        AccountTax = self.env['account.tax']

        related_sales = self.get_related_sales()
        amount = sum(related_sales.mapped('amount_man'))

        if tools.float_is_zero(amount, precision_digits=2):
            return AccountTax

        vat_sum = sum(related_sales.mapped('vat_sum_man'))

        sum_wo_vat = amount - vat_sum
        sum_wo_vat = 1 if tools.float_is_zero(sum_wo_vat, precision_digits=2) else sum_wo_vat
        tax_percentage = round(((amount / sum_wo_vat) - 1) * 100, 0)
        return AccountTax.search([
            ('amount', '=', tax_percentage),
            ('type_tax_use', '=', 'sale'),
            ('price_include', '=', True)
        ], limit=1)

    @api.multi
    def find_related_account_tax(self, manual_taxes=False):
        """
        Find account.tax record for the raso sale line, based on
        forced tax code, or percentage that is calculated from
        other sale amounts
        :return: account.tax record, True/False (depending on if taxes should be forced)
        """
        self.ensure_one()
        related_taxes = AccountTax = self.env['account.tax']
        force_taxes = False

        # Use different fields depending on whether taxes to be searched are manual or not
        amount = self.amount_man if manual_taxes else self.amount
        vat_sum = self.vat_sum_man if manual_taxes else self.vat_sum

        base_tax_domain = [('type_tax_use', '=', 'sale'), ('price_include', '=', True)]
        # If line contains forced taxes, find related record by code
        forced_tax_code = PRODUCT_TO_FORCED_TAX_MAPPING.get(self.code)
        if forced_tax_code:
            related_taxes = AccountTax.search(
                [('code', '=', forced_tax_code)] + base_tax_domain, limit=1)
            force_taxes = True
        # else, if amount of the line is not zero, try to calculate the percentage
        elif not tools.float_is_zero(amount, precision_digits=2):
            sum_wo_vat = amount - vat_sum
            sum_wo_vat = 1 if tools.float_is_zero(sum_wo_vat, precision_digits=2) else sum_wo_vat
            percentage = round(((amount / sum_wo_vat) - 1) * 100, 0)
            related_taxes = AccountTax.search([('amount', '=', percentage)] + base_tax_domain, limit=1)

            likely_incorrect_manual_vat_sum = manual_taxes and \
                                              tools.float_compare(abs(vat_sum), 0.01, precision_digits=2) <= 0
            if not related_taxes and likely_incorrect_manual_vat_sum:
                related_taxes = self.find_manual_tax_based_on_related_sales()

            # If corresponding taxes were not found, try to round the percentage to the nearest one
            # accepted percentages are 21, 9 and 5. If percentage is not in these ranges, continue
            if not related_taxes:
                force_taxes = True
                if 15 <= percentage <= 30:
                    base_tax_domain.append(('amount', '=', 21))
                elif 7 <= percentage < 15:
                    base_tax_domain.append(('amount', '=', 9))
                elif 3 <= percentage < 7:
                    base_tax_domain.append(('amount', '=', 5))
                elif likely_incorrect_manual_vat_sum:
                    base_tax_domain.append(('amount', '=', 21))  # Force 21% VAT for manual VAT amounts of 0.01 or less
                elif manual_taxes and self.tax_id:
                    return self.tax_id, False  # No way to calculate the manual taxes but regular taxes exist.
                elif tools.float_compare(sum_wo_vat, vat_sum, precision_digits=2) <= 0:
                    # Force 21% VAT for amounts where VAT amount is more than or equal to sum without VAT.
                    base_tax_domain.append(('amount', '=', 21))
                else:
                    return AccountTax, False
                related_taxes = AccountTax.search(base_tax_domain, limit=1)

        return related_taxes, force_taxes

