# -*- coding: utf-8 -*-

from odoo import models


class AccountSepaImport(models.TransientModel):

    _inherit = 'account.sepa.import'

    def get_partner_id(self, partner_name='', partner_identification='', partner_iban='', ext_id=''):
        if ext_id:
            try:
                ext_id = int(ext_id)
            except ValueError:
                ext_id = False
        if ext_id:
            partner_id = self.env['res.partner'].search([('gemma_ext_id', '=', ext_id)]).id
        else:
            partner_id = False
        if not partner_id:
            partner_id = super(AccountSepaImport, self).get_partner_id(
                partner_name=partner_name,
                partner_identification=partner_identification,
                partner_iban=partner_iban)
        return partner_id


AccountSepaImport()
