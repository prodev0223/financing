# -*- coding: utf-8 -*-
from odoo import models, api, fields
from unidecode import unidecode

# Hardcoded BIC for šiaulių bankas, it does not work correctly most
# of the time, so it's preferred for it to be skipped
NON_PREFERRED_BIC = 'CBSBLT26XXX'


class ResPartner(models.Model):

    _inherit = 'res.partner'

    mokesciu_institucija = fields.Boolean(string='Mokesčių institucija', default=False)
    imokos_kodas = fields.Char(string='Kliento įmokos kodas')

    substitute_bank_export_partner_id = fields.Many2one(
        'res.partner', string='Pakaitinis partneris (Bankinis eksportavimas)',
        help='Pasirinktas partneris bus naudojamas sąskaitų banko eksportavimo operacijose vietoje esamo partnerio'
    )
    substitute_bank_export_name = fields.Char(
        string='Pakaitinis pavadinimas (Bankinis eksportavimas)',
        help='Įrašytas pavadinimas bus naudojamas sąskaitų banko eksportavimo operacijose vietoje pagr. pavadinimo'
    )

    @api.multi
    def get_bank_export_name(self):
        """Returns partner name to use in bank export"""
        self.ensure_zero_or_one()
        # Check whether partner is from foreign country or not
        # and if it is unidecode bank export name
        foreign_country = self.country_id and self.country_id != self.env.user.company_id.country_id
        bank_export_name = self.substitute_bank_export_name or self.name
        if foreign_country and bank_export_name:
            if isinstance(bank_export_name, str):
                bank_export_name = unicode(bank_export_name, encoding='utf-8')
            bank_export_name = unidecode(bank_export_name)
        return bank_export_name

    @api.multi
    def get_bank_export_partner(self):
        """
        Get the partner for bank export.
        If forced partner is set, return it, otherwise current record
        :return: res.partner record
        """
        self.ensure_zero_or_one()
        return self.substitute_bank_export_partner_id or self

    @api.multi
    def get_preferred_bank(self, journal):
        """
        Get preferred bank account for specific partner
        Criteria -- if partner has bank accounts, search for bank that matches
        the journal, if it exists, fetch preferred bank, otherwise first bank
        of the list
        :param journal: account.journal record
        :return: res.partner.bank record
        """
        self.ensure_one()
        final_bank_account = self.env['res.partner.bank']
        bank_accounts = self.bank_ids
        if bank_accounts:
            preferred_bank = journal.bank_id if journal else final_bank_account
            bank_account = bank_accounts.filtered(lambda r: r.active and r.bank_id.id == preferred_bank.id)
            if not bank_account:
                if self.is_employee and self.employee_ids and self.employee_ids[0].bank_account_id:
                    bank_account = self.employee_ids[0].bank_account_id
                else:
                    bank_account = bank_accounts.filtered(lambda r: r.active and r.bank_id.bic != NON_PREFERRED_BIC)
            final_bank_account = bank_account[0] if bank_account else bank_accounts[0]
        return final_bank_account

    @api.multi
    def get_bank_export_address(self):
        """Returns partner address to use in bank export"""
        self.ensure_zero_or_one()
        # Check whether partner is from foreign country or not
        # and if it is unidecode, sanitize the address
        foreign_country = self.country_id and self.country_id != self.env.user.company_id.country_id
        bank_export_address = self.street or '-'
        if foreign_country and bank_export_address:
            if isinstance(bank_export_address, str):
                bank_export_address = unicode(bank_export_address, encoding='utf-8')
            bank_export_address = unidecode(bank_export_address)
        return bank_export_address
