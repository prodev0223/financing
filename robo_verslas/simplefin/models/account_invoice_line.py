# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    is_coverage = fields.Boolean(compute='_compute_is_coverage')

    @api.multi
    def is_coverage_line(self):
        """
        Decide if the product of the given line belongs to loan coverage category;
        :return: Boolean, True if line is a coverage line;
        """
        self.ensure_one()
        category_id = self.env.ref('simplefin.simplefin_product_category_coverage', raise_if_not_found=False).id
        if not category_id:
            return False
        return self.product_id.product_tmpl_id.categ_id.id == category_id

    @api.multi
    def _compute_is_coverage(self):
        for rec in self:
            rec.is_coverage = rec.is_coverage_line()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        When product_id is changed on invoice line, set the taxes of coverage lines to taxes not subject to VAT;
        """
        vals = super(AccountInvoiceLine, self)._onchange_product_id()
        account_tax_domain_base = [
            ('code', '=', 'Ne PVM'),
            ('price_include', '=', False),
        ]
        for rec in self:
            account_tax_domain = list(account_tax_domain_base)
            invoice_type = 'sale' if rec.invoice_id.type in ['out_invoice', 'out_refund'] else 'purchase'
            account_tax_domain.append(
                ('type_tax_use', '=', invoice_type)
            )
            tax_ids = self.env['account.tax'].search(account_tax_domain).ids
            if rec.product_id and rec.is_coverage:
                rec.invoice_line_tax_ids = [(6, 0, tax_ids)]
        return vals
