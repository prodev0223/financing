# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'
    activity_number = fields.Char(string='Individualios veiklos pažymėjimo numeris')
    activity_number_annotation = fields.Boolean(
        string='Spausdinti individualios veiklos pažymėjimo numerį', default=True)

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        company_id = self.sudo().env.user.company_id
        res['activity_number'] = company_id.activity_number
        res['activity_number_annotation'] = company_id.activity_number_annotation
        return res

    @api.multi
    def set_company_info(self):
        if not self.env.user.is_manager():
            return False
        self.ensure_one()
        res = super(CompanySettings, self).set_company_info()
        self.env.user.company_id.sudo().write({
            'activity_number': self.activity_number,
            'activity_number_annotation': self.activity_number_annotation
            })
        return res


CompanySettings()


class ResCompany(models.Model):
    _inherit = 'res.company'
    activity_number = fields.Char(string='Individualios veiklos pažymėjimo numeris')
    activity_number_annotation = fields.Boolean(
        string='Spausdinti individualios veiklos pažymėjimo numerį', default=True)


ResCompany()


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    walless_main_ext_id = fields.Integer(string='Išorinis Walless sąskaitos ID')

    @api.onchange('payment_mode', 'ap_employee_id')
    def onchange_payment_mode(self):
        pass  # overridden from robo module, don't use any partner_id domains in walless_partners


AccountInvoice()


class EVmiFr0600(models.TransientModel):
    _inherit = 'e.vmi.fr0600'

    @api.multi
    def post_process_data(self, data):
        super(EVmiFr0600, self).post_process_data(data)
        data['uz_lt_ribu'] = 0


EVmiFr0600()
