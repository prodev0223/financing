# -*- coding: utf-8 -*-
from odoo import models, api, fields


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    license_number = fields.Char(string='Kliento licencijos numeris', inverse='_set_license_number')

    @api.multi
    def _set_license_number(self):
        """
        Force license number from the invoice to partner if
        it's not set in the partner card
        """
        for rec in self:
            if rec.license_number and not rec.partner_id.license_number:
                rec.partner_id.license_number = rec.license_number

    @api.onchange('partner_id')
    def _onchange_partner_id_license(self):
        """Set license number based on partner"""
        license_number = False
        if self.partner_id:
            license_number = self.partner_id.license_number
        self.license_number = license_number
