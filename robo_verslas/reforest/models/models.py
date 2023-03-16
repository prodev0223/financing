# -*- coding: utf-8 -*-
from odoo import models, api, _


class NsoftInvoice(models.Model):

    _inherit = 'nsoft.invoice'

    # Overridden from NSOFT module
    @api.one
    def get_partner(self):
        if not self.partner_id and self.cash_register_id:
            if self.partner_name or self.partner_code:
                partner_id = self.env['res.partner']
                if self.partner_name:
                    self.partner_id = self.env['res.partner'].search([('name', '=', self.partner_name)], limit=1)
                if not partner_id and self.partner_code:
                    self.partner_id = self.env['res.partner'].search([('kodas', '=', self.partner_code)], limit=1)
                if not partner_id:
                    country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                    partner_vals = {
                        'name': self.partner_name,
                        'is_company': False,
                        'kodas': self.partner_code,
                        'phone': self.partner_mobile,
                        'vat': self.partner_vat,
                        'street': self.partner_address or ' ',
                        'country_id': country_id.id,
                        'property_account_receivable_id': self.env['account.account'].sudo().search([('code', '=', '2410')],
                                                                                                    limit=1).id,
                        'property_account_payable_id': self.env['account.account'].sudo().search([('code', '=', '4430')],
                                                                                                 limit=1).id,
                    }
                    try:
                        self.partner_id = self.env['res.partner'].sudo().create(partner_vals).id
                    except Exception as e:
                        self.state = 'failed2'
                        msg = {
                            'body': _("Klaida, netinkami partnerio duomenys, klaidos pranešimas %s") % str(e.args[0]),
                        }
                        self.message_post(**msg)
                else:
                    self.partner_id.name = self.partner_name
                    self.partner_id.kodas = self.partner_code
            else:
                self.partner_id = self.cash_register_id.partner_id
            if self._context.get('force_commit', False):
                self.env.cr.commit()


NsoftInvoice()
