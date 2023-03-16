# -*- coding: utf-8 -*-
from odoo.addons.robo.models.robo_tools import sanitize_account_number
from odoo import api, fields, models


class RoboCompanySettingsBank(models.TransientModel):
    _name = 'robo.company.settings.bank'

    company_bank_account = fields.Char(string='Banko sąskaita')
    company_bank_name = fields.Char(string='Pavadinimas')
    company_bank_code = fields.Char(string='Kodas')
    company_bank_bic = fields.Char(string='BIC')
    company_bank_currency = fields.Many2one('res.currency', string='Valiuta', required=True)
    show_footer = fields.Boolean(string='Spausdinti sąskaitoje')
    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    settings_id = fields.Many2one('robo.company.settings')

    @api.onchange('company_bank_account')
    def onchange_company_bank_account(self):
        if self.company_bank_account:
            self.company_bank_account = sanitize_account_number(self.company_bank_account)
        if self.company_bank_account and len(self.company_bank_account) >= 9:
            # Search for the bank, and if it's not found, use three instead of 5 digits
            code_search = [(self.company_bank_account[4:9], '='), (self.company_bank_account[4:7], '=like')]
            for code, operator in code_search:
                res_bank = self.sudo().env['res.bank'].search([('kodas', operator, code + '%')], limit=1)
                if res_bank:
                    self.company_bank_bic = res_bank.bic
                    self.company_bank_code = res_bank.kodas
                    self.company_bank_name = res_bank.name
                    break
