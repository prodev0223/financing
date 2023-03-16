# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models
from datetime import datetime


class AccountInvoiceTax(models.Model):
    _inherit = 'account.invoice.tax'

    tax_id = fields.Many2one(required=True)
    base_signed = fields.Monetary(string='Base Signed', compute='_signed', store=True)
    amount_signed = fields.Monetary(string='Amount Signed', compute='_signed', store=True)
    base = fields.Monetary(string='Base', compute='_compute_base_amount')

    @api.one
    @api.depends('invoice_id.company_id.currency_id', 'currency_id', 'invoice_id.currency_id',
                 'invoice_id.date_invoice', 'amount', 'base')
    def _signed(self):
        company_currency = self.invoice_id.company_id.currency_id
        if company_currency.id == self.currency_id.id:
            self.base_signed = self.base
            self.amount_signed = self.amount
        else:
            date = self.invoice_id.operacijos_data or self.invoice_id.date_invoice or datetime.utcnow()
            self.base_signed = self.currency_id.with_context(date=date).compute(self.base, company_currency)
            self.amount_signed = self.currency_id.with_context(date=date).compute(self.amount, company_currency)

    @api.onchange('tax_id')
    def _onchange_tax_id(self):
        self.name = self.tax_id.name if self.tax_id else ''
        if self.tax_id.account_id:
            self.account_id = self.tax_id.account_id

    @api.constrains('invoice_id', 'tax_id', 'account_analytic_id', 'account_id')
    def _check_unique_grouping_key(self):
        """ Prevent similar invoice tax lines, as they would get the same base amount """
        for rec in self:
            if self.search_count([('invoice_id', '=', rec.invoice_id.id),
                                  ('tax_id', '=', rec.tax_id.id),
                                  ('account_analytic_id', '=', rec.account_analytic_id.id),
                                  ('account_id', '=', rec.account_id.id),
                                  ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(
                    _('There is already a line for these tax, account, and analytic account (%s, %s, %s)')
                    % (rec.tax_id.name, rec.account_id.code, rec.account_analytic_id.name))
