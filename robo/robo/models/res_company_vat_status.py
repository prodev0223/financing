# -*- coding: utf-8 -*-


from odoo import fields, models


class ResCompanyVatStatus(models.Model):
    _inherit = 'res.company.vat.status'

    attachment = fields.Binary(string='Prisegtas failas')
    file_name = fields.Char(string='Failo pavadinimas')
