# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompanyShareholder(models.Model):
    _name = 'res.company.shareholder'
    _description = 'Company Shareholders'

    _order = 'shareholder_shares'

    def default_company_id(self):
        return self.env.ref('base.main_company')

    company_id = fields.Many2one('res.company', string='Company', required=True, default=default_company_id, lt_string='Kompanija')
    shareholder_name = fields.Char(string='Name', required=True, lt_string='Vardas Pavardė / Pavadinimas')
    shareholder_address = fields.Text(string='Address', lt_string='Adresas')
    shareholder_personcode = fields.Char(string='Personnal Code', required=True, lt_string='Asmens/įmonės kodas')
    shareholder_shares = fields.Float(string='Number of shares', required=True, lt_string='Akcijų skaičius')
    shareholder_type = fields.Selection([('person', 'Fizinis asmuo'),
                                         ('company', 'Juridinis Asmuo')],
                                        string='Akcininko tipas', default='person')

    @api.multi
    def name_get(self):
        return [(rec.id, rec.shareholder_name) for rec in self]


ResCompanyShareholder()
