# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    # TODO Move to robo?
    inline_company_address = fields.Text(compute='_compute_inline_company_address')
    inline_partner_address = fields.Text(compute='_compute_inline_partner_address')

    @api.multi
    @api.depends('company_id.partner_id')
    def _compute_inline_company_address(self):
        partners = self.mapped('company_id.partner_id')
        for partner in partners:
            invoices_with_partner = self.filtered(lambda acc_inv: acc_inv.company_id.partner_id == partner)
            partner_address_formatted = self.format_address_for_partner(partner)
            for invoice in invoices_with_partner:
                invoice.inline_company_address = partner_address_formatted

    @api.multi
    @api.depends('partner_id')
    def _compute_inline_partner_address(self):
        partners = self.mapped('partner_id')
        for partner in partners:
            invoices_with_partner = self.filtered(lambda acc_inv: acc_inv.partner_id == partner)
            partner_address_formatted = self.format_address_for_partner(partner)
            for invoice in invoices_with_partner:
                invoice.inline_partner_address = partner_address_formatted

    @api.model
    def format_address_for_partner(self, partner):
        if not partner:
            return ''
        address_vals = [partner.street, partner.street2, partner.zip, partner.city]
        if partner.country_id and partner.country_id.code != 'LT':
            address_vals.append(partner.country_id.name)
        return ', '.join([val for val in address_vals if val])
