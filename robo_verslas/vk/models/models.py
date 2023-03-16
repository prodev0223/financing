# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions


# TODO REMOVE NEXT WEEK
class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'
    licence = fields.Char(string='Kompanijos licencijos numeris')

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        company_id = self.sudo().env.user.company_id
        res['licence'] = company_id.licence
        return res

    @api.multi
    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
        self.ensure_one()
        res = super(CompanySettings, self).set_company_info()
        self.env.user.company_id.sudo().write({
            'licence': self.licence})
        return res


CompanySettings()
# // TODO REMOVE NEXT WEEK


class ResCompany(models.Model):
    _inherit = 'res.company'
    licence = fields.Char(string='Kompanijos licencijos numeris')  # TODO REMOVE NEXT WEEK
    analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                  lt_string='Analitinė sąskaita')


ResCompany()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'
    al_annotation = fields.Boolean(string='Spausdinti alkoholinių gėrimų pastabą', default=True)
    client_licence = fields.Char(string='Kliento licencijos numeris', inverse='_set_partner_licence')  # TODO REMOVE NEXT WEEK
    delivery_address = fields.Char(string='Pristatymo adresas', compute='_compute_delivery_address')

    @api.one
    def _set_partner_licence(self):
        if self.client_licence:  # TODO REMOVE NEXT WEEK
            self.sudo().partner_id.mobile = self.client_licence

    @api.one
    def _compute_delivery_address(self):
        if self.sale_ids and self.sale_ids[0].partner_shipping_id.id != self.partner_id.id:
            self.delivery_address = self.sale_ids[0].partner_shipping_id.contact_address

    @api.onchange('partner_id')
    def change_licence(self):
        if self.partner_id:   # TODO REMOVE NEXT WEEK
            self.client_licence = False
            if self.partner_id.client_licence:
                self.client_licence = self.partner_id.client_licence


AccountInvoice()


# TODO REMOVE NEXT WEEK
class ResPartner(models.Model):

    _inherit = 'res.partner'
    client_licence = fields.Char(string='Licencijos numeris')


ResPartner()
# TODO REMOVE NEXT WEEK
