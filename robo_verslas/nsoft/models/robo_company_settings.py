# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class CompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    nsoft_accounting_threshold_date = fields.Datetime(string='Apskaitos pradžios data')
    nsoft_accounting_type = fields.Selection([
        ('sum', 'Suminė'), ('detail', 'Detali')],
        string='nSoft Apskaitos tipas', default='detail'
    )
    enable_nsoft_cash_operations = fields.Boolean(string='Enable nSoft cash operations')

    @api.model
    def default_get(self, field_list):
        res = super(CompanySettings, self).default_get(field_list)
        company = self.env.user.sudo().company_id
        res.update({
            'enable_nsoft_cash_operations': company.enable_nsoft_cash_operations,
            'nsoft_accounting_type': company.nsoft_accounting_type,
            'nsoft_accounting_threshold_date': company.nsoft_accounting_threshold_date,
        })
        return res

    @api.multi
    def save_nsoft_settings(self):
        """
        Write nSoft configuration settings to res.company record
        :return: None
        """
        self.ensure_one()

        # Managers can see the values, but they can't modify them
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Tik buhalteris gali keisti nSoft nustatymus!'))
        self.env.user.company_id.sudo().write({
            'nsoft_accounting_threshold_date': self.nsoft_accounting_threshold_date,
            'nsoft_accounting_type': self.nsoft_accounting_type,
            'enable_nsoft_cash_operations': self.enable_nsoft_cash_operations,
        })
