# -*- coding: utf-8 -*-
from odoo import api, fields, models
from .gpais_commons import PRODUCT_TYPES


class GpaisKlasifikacija(models.Model):
    _name = 'gpais.klasifikacija'

    name = fields.Char(string='Pavadinimas')
    code = fields.Char(string='Kodas')
    product_type = fields.Selection(PRODUCT_TYPES, string='Produkto tipas')
    code_class = fields.Char(string='Klasė', compute='_code_class', store=True)

    @api.one
    @api.depends('code')
    def _code_class(self):
        if self.code and ':' in self.code:
            self.code_class = self.code.split(':')[0]
