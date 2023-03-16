# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    license_number = fields.Char(string='Kompanijos licencijos numeris')
