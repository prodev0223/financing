# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, exceptions, fields, models, _
from odoo.tools import float_is_zero


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    show_coverage_amount = fields.Boolean(compute='_compute_show_coverage_amount')
    coverage_type = fields.Char(compute='_compute_coverage_type')

    amount_coverage = fields.Monetary(
        string='Coverage amount', store=True, readonly=True, compute='_compute_amount', track_visibility='always',
        sequence=100, )
    amount_coverage_company_signed = fields.Monetary(
        string='Coverage amount in company currency', currency_field='company_currency_id', store=True, readonly=True,
        compute='_compute_amount', help='Amount coverage in the currency of the company', sequence=100, )
    reporting_amount_coverage = fields.Monetary(string='Coverage amount', compute='_reporting_amounts')
    print_amount_coverage = fields.Monetary(string='Coverage amount', compute='_compute_print_amounts')
    print_amount_coverage_company = fields.Monetary(string='Coverage amount company currency',
                                                    compute='_compute_print_amounts',
                                                    currency_field='company_currency_id')
    print_amount_total_company_included_coverage = fields.Monetary(string='Suma su mokesčiais',
                                                                   compute='_compute_print_amounts',
                                                                   currency_field='company_currency_id')

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        account_tax_domain = [
            ('code', '=', 'Ne PVM'),
            ('price_include', '=', False),
        ]
        for rec in self:
            # Find not subject to VAT tax;
            account_tax_domain.append(
                ('type_tax_use', '=', 'sale' if rec.type in ['out_invoice', 'out_refund'] else 'purchase')
            )
            tax_ids = self.env['account.tax'].search(account_tax_domain).ids
            if not tax_ids:
                continue
            # Get only coverage lines for all invoice lines;
            coverage_lines = rec.get_coverage_lines()
            if not coverage_lines:
                continue
            # Ensure that lines consist of no more than one coverage type
            coverage_type_count = len(list(set(coverage_lines.mapped('product_id'))))
            if coverage_type_count > 1:
                raise exceptions.ValidationError(_('An invoice can not have more than one coverage type.'))
            # Adjust coverage line tax ids;
            coverage_lines_with_tax = coverage_lines.filtered(
                lambda l: l.invoice_line_tax_ids and any(
                    not float_is_zero(tax_id.amount, precision_rounding=4) for tax_id in l.invoice_line_tax_ids)
            )
            if not coverage_lines_with_tax:
                continue
            coverage_lines_with_tax.write({'invoice_line_tax_ids': [(6, 0, tax_ids)]})
        return res

    @api.multi
    def get_coverage_lines(self):
        """
        Method to return only coverage lines from the current invoice lines;
        :return: coverage lines if they are found, otherwise - empty recordset;
        """
        self.ensure_one()
        category_id = self.env.ref('simplefin.simplefin_product_category_coverage', raise_if_not_found=False).id
        if not category_id:
            return self.env['account.invoice.line']
        lines = self.invoice_line_ids.filtered(lambda l: category_id == l.product_id.product_tmpl_id.categ_id.id)
        return lines

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line(self):
        self._compute_show_coverage_amount()

    @api.multi
    @api.depends('invoice_line_ids')
    def _compute_show_coverage_amount(self):
        for rec in self:
            rec.show_coverage_amount = rec.get_coverage_lines()

    @api.multi
    @api.depends('invoice_line_ids')
    def _compute_coverage_type(self):
        """
        Method to set the type of coverage to use later for the additional line on invoice PDF;
        """
        coverage_leasing = self.env.ref('simplefin.simplefin_product_leasing_coverage', raise_if_not_found=False)
        coverage_loan = self.env.ref('simplefin.simplefin_product_loan_coverage', raise_if_not_found=False)
        if not coverage_leasing or not coverage_loan:
            return
        type_mapper = {
            coverage_loan.id: _('Asset value coverage according to schedule'),
            coverage_leasing.id: _('Repayment of part of the loan according to schedule'),
        }
        for rec in self.filtered(lambda l: l.show_coverage_amount):
            coverage_line_product_ids = list(set(rec.get_coverage_lines().mapped('product_id')))
            key = coverage_line_product_ids[0].product_tmpl_id.id if coverage_line_product_ids else False
            if key and key in type_mapper.keys():
                rec.coverage_type = type_mapper[key]

    # ----- Compute amounts ------
    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'currency_id', 'company_id', 'date_invoice',
                 'price_include_selection')
    def _compute_amount(self):
        res = super(AccountInvoice, self)._compute_amount()
        for rec in self:
            # Get coverage lines and calculate their sum
            coverage_lines = rec.get_coverage_lines()
            if not coverage_lines:
                continue
            rec.amount_coverage = sum(coverage_lines.mapped('price_subtotal')) if coverage_lines else 0.0
            # Subtract coverage amount from the total amount untaxed
            rec.amount_untaxed = rec.amount_untaxed - rec.amount_coverage
            # Calculate coverage amount in company currency
            amount_coverage_company_signed = rec.amount_coverage
            if rec.currency_id and rec.currency_id != rec.company_id.currency_id:
                date = rec.operacijos_data or rec.date_invoice or datetime.utcnow()
                amount_coverage_company_signed = rec.currency_id.with_context(date=date).compute(
                    rec.amount_coverage, rec.company_id.currency_id)
            sign = rec.type in ['in_refund', 'out_refund'] and -1 or 1
            rec.amount_coverage_company_signed = amount_coverage_company_signed * sign
        return res

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'tax_line_ids')
    def _reporting_amounts(self):
        res = super(AccountInvoice, self)._reporting_amounts()
        for rec in self:
            rec.reporting_amount_coverage = rec.amount_coverage
        return res

    @api.multi
    @api.depends('type', 'currency_id', 'date_invoice')
    def _compute_print_amounts(self):
        res = super(AccountInvoice, self)._compute_print_amounts()
        for rec in self:
            sign = -1.0 if 'refund' in rec.type else 1.0
            # Calculate coverage amount
            rec.print_amount_coverage = rec.amount_coverage * sign
            rec.print_amount_coverage_company = rec.amount_coverage_company_signed * sign
            # Calculate amount untaxed and total, exclude amount coverage
            rec.print_amount_total = rec.print_amount_total - rec.print_amount_coverage
            # Company currency
            rec.print_amount_untaxed_company = rec.print_amount_untaxed_company - rec.print_amount_coverage_company
            rec.print_amount_total_company_included_coverage = rec.print_amount_total_company
            rec.print_amount_total_company = rec.print_amount_total_company - rec.print_amount_coverage_company
        return res
