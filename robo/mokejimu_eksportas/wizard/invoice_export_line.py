# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api


class ExportInvoiceLine(models.TransientModel):
    _name = 'invoice.export.line'

    company_id = fields.Many2one('res.company', string='Kompanija')
    date = fields.Date(string='Data')
    name = fields.Char(string='Mokėjimo paskirtis')
    ref = fields.Char(string='Nuoroda')
    amount = fields.Float(string='Suma')
    partner_id = fields.Many2one('res.partner', string='Partneris', ondelete="cascade")
    currency_id = fields.Many2one('res.currency', string='Valiuta', ondelete="cascade")
    invoice_ids = fields.Many2many('account.invoice', string='Sąskaitos', ondelete="cascade")
    aml_ids = fields.Many2many('account.move.line', string='Eilutės', ondelete="cascade")
    bank_account_id = fields.Many2one('res.partner.bank', string='Banko sąskaita', ondelete="cascade")
    account_id = fields.Many2one('account.account', string='Sąskaita', ondelete="cascade", inverse='_set_account_id')
    info_type = fields.Selection([
        ('unstructured', 'Nestruktūruota'),
        ('structured', 'Struktūruota')],
        default='unstructured', string='Mokėjimo paskirties struktūra'
    )

    # Partial payment fields
    partial_payment = fields.Boolean(string='Dalinis mokėjimas', compute='_compute_partial_payment')
    post_export_residual = fields.Float(compute='_compute_partial_payment')
    has_multiple_bank_accounts = fields.Boolean(compute='_compute_has_multiple_bank_accounts')
    html_warning_icon = fields.Html(compute='_compute_html_warning_icon', string='Warning')

    @api.multi
    @api.depends('amount')
    def _compute_partial_payment(self):
        """
        Compute whether lines to be exported are partial payments or full payments.
        If payments is partial, compute post residual amount: current invoice residual - export sum
        and partial payment html badge
        :return: None
        """
        for rec in self:
            amt_total_residual = 0.0
            # Calculate either from invoices or move lines
            if self._context.get('active_model') == 'account.invoice':
                for invoice_id in rec.invoice_ids:
                    refund = bool(invoice_id.type in ['out_invoice', 'in_refund'])
                    own_acc_paid = bool(invoice_id.state not in ['open', 'proforma', 'proforma2']
                                        and invoice_id.payment_mode == 'own_account'
                                        and not invoice_id.is_cash_advance_repaid)
                    if own_acc_paid:
                        amt_total_residual += invoice_id.amount_total_company_signed
                    else:
                        amt_total_residual += invoice_id.bank_export_residual \
                            if not refund else invoice_id.bank_export_residual * -1
            else:
                for line in rec.aml_ids:
                    amt_total_residual += line.bank_export_residual

            rec.post_export_residual = amt_total_residual - rec.amount
            rec.partial_payment = True if tools.float_compare(
                amt_total_residual, rec.amount, precision_digits=2) == 1 else False  # Also False on overpayment

    @api.multi
    def _set_account_id(self):
        """
        Inverse //
        If account has structured code,
        change info type and reference
        :return: None
        """
        for rec in self:
            if rec.account_id.structured_code:
                rec.info_type = 'structured'
                rec.ref = rec.account_id.structured_code

    @api.onchange('partner_id')
    def check_bank_account_on_partner_change(self):
        self.bank_account_id = False

    @api.multi
    def _compute_has_multiple_bank_accounts(self):
        for rec in self:
            bank_ids = rec.partner_id.mapped('bank_ids')
            if len(bank_ids) > 1:
                rec.has_multiple_bank_accounts = True

    @api.multi
    def _compute_html_warning_icon(self):
        for rec in self:
            rec.html_warning_icon = '<i class="fa fa-solid fa-exclamation" style="color:red"></i>'
