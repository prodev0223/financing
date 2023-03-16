# -*- coding: utf-8 -*-
from odoo import fields, models, api


class InvoiceMassMailingWizardLine(models.TransientModel):
    """
    Transient model that holds lines (invoices) to-be-mailed
    with mass mailing wizard
    """
    _name = 'invoice.mass.mailing.wizard.line'

    # Relational fields
    mass_mailing_wizard_id = fields.Many2one('invoice.mass.mailing.wizard')
    invoice_id = fields.Many2one('account.invoice', string='Sąskaita', inverse='_set_partner_ids')
    partner_ids = fields.Many2many('res.partner', string='Gavėjai')
    currency_id = fields.Many2one('res.currency', string='Sąskaitos valiuta', compute='_compute_currency_id')

    # Other fields
    amount = fields.Float(string='Sąskaitos suma', compute='_compute_amount')
    generated_pdf = fields.Binary(string='Sąskaita PDF', attachment=True, readonly=True)
    file_name = fields.Char(string='Failo pavadinimas')

    @api.multi
    def _set_partner_ids(self):
        """
        Inverse //
        One invoice can be mailed to several partners just as in single record
        send mail wizard. However we set the invoice partner as default.
        :return: None
        """
        for rec in self:
            rec.partner_ids = [(6, 0, rec.invoice_id.partner_id.ids)]

    @api.multi
    @api.depends('invoice_id')
    def _compute_currency_id(self):
        """
        Compute //
        Get display currency from related account_invoice record
        :return: None
        """
        for rec in self:
            rec.currency_id = rec.invoice_id.currency_id

    @api.multi
    @api.depends('invoice_id')
    def _compute_amount(self):
        """
        Compute //
        Get display amount from related account_invoice record
        :return: None
        """
        for rec in self:
            rec.amount = rec.invoice_id.amount_total_signed


InvoiceMassMailingWizardLine()
