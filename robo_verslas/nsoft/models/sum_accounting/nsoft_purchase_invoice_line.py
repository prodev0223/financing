
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools
from .. import nsoft_tools


class NsoftPurchaseInvoiceLine(models.Model):
    """
    Model that stores purchase invoice line data fetched from external nSoft database
    -- USED IN SUM ACCOUNTING
    """
    _name = 'nsoft.purchase.invoice.line'
    _inherit = ['nsoft.sum.accounting.line.base', 'mail.thread']

    # Sums
    amount_wo_vat = fields.Float(string='Suma (Be PVM)')
    amount_w_vat = fields.Float(string='Suma (Su PVM)')
    amount_vat = fields.Float(string='PVM suma')

    # Other fields
    vat_rate = fields.Float(string='PVM Procentas', inverse='_set_tax_id')
    state = fields.Selection([('imported', 'Eilutė importuota'),
                              ('created', 'Eilutė sukurta sistemoje'),
                              ('failed', 'Klaida kuriant eilutę')],
                             string='Būsena', default='imported', track_visibility='onchange')

    # Relational Fields
    invoice_line_id = fields.Many2one('account.invoice.line', string='Sąskaitos faktūros eilutė')
    product_id = fields.Many2one('product.product', string='Produktas', compute='_compute_product_id', store=True)
    invoice_id = fields.Many2one('account.invoice', string='Saskaita faktūra', compute='_compute_invoice_id')
    nsoft_purchase_invoice_id = fields.Many2one('nsoft.purchase.invoice', string='nSoft pirkimo sąskaita')
    tax_id = fields.Many2one('account.tax', string='PVM')

    # Computes / Inverses --------------------------------------------------------------------------------------

    @api.multi
    @api.depends('nsoft_product_category_id.parent_product_id', 'nsoft_product_category_id')
    def _compute_product_id(self):
        """Compute"""
        for rec in self:
            rec.product_id = rec.nsoft_product_category_id.parent_product_id

    @api.multi
    def _set_tax_id(self):
        """
        Find corresponding account.tax record based on vat_rate and set tax_id field.
        If vat_rate matches static value search by account.tax code.
        If product category has forced account.tax, check the amounts, if they match
        use forced taxes otherwise use regular record
        :return: None
        """
        for rec in self:
            # Check forced taxes - one can be set in category, the other one in partner
            category_forced_account_tax = rec.nsoft_product_category_id.forced_tax_id
            partner_forced_account_tax = rec.nsoft_purchase_invoice_id.partner_id.forced_nsoft_purchase_tax_id
            # Determine forced tax account, give priority to category account
            account_tax_forced = category_forced_account_tax or partner_forced_account_tax
            domain = [('type_tax_use', '=', 'purchase'), ('price_include', '=', True)]

            # If external VAT rate is zero, but VAT amount is not -External inconsistencies,
            # VAT amount must be calculated artificially.
            vat_rate = rec.vat_rate
            if tools.float_is_zero(
                    rec.vat_rate, precision_digits=2) and not tools.float_is_zero(
                    rec.amount_vat, precision_digits=2
            ):
                # Calculate artificial rate
                vat_rate = round(((rec.amount_w_vat / rec.amount_wo_vat) - 1) * 100, 0)

            code = nsoft_tools.VAT_RATE_TO_CODE_MAPPER.get(vat_rate)
            domain.append(('code', '=', code)) if code else domain.append(('amount', '=', vat_rate))
            account_tax = self.env['account.tax'].search(domain, limit=1)
            if account_tax_forced and account_tax and not tools.float_compare(
                    account_tax_forced.amount, account_tax.amount, precision_digits=2):
                if account_tax_forced.type_tax_use != 'purchase' or not account_tax_forced.price_include:
                    account_tax_forced = account_tax_forced.find_matching_tax_varying_settings(type_tax_use='purchase')
                account_tax = account_tax_forced
            rec.tax_id = account_tax

    @api.multi
    @api.depends('invoice_line_id')
    def _compute_invoice_id(self):
        """Compute"""
        for rec in self:
            rec.invoice_id = rec.invoice_line_id.invoice_id

    @api.multi
    def recompute_fields(self):
        """
        Recalculate every inverse/compute field in the model
        :return:
        """
        super(NsoftPurchaseInvoiceLine, self).recompute_fields()
        self._set_tax_id()
        self._compute_product_id()
        self._compute_invoice_id()


NsoftPurchaseInvoiceLine()
