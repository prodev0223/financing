# -*- coding: utf-8 -*-

from odoo import models, fields, api


class GemmaVatMapper(models.Model):
    _name = 'gemma.vat.mapper'

    cash_register_id = fields.Many2one('gemma.cash.register', string='Gemma Kasos aparatas')
    ext_code = fields.Char(string='Gemma PVM Kodas')
    int_code = fields.Char(string='Vidinis PVM Kodas')
    tax_id = fields.Many2one('account.tax', string='PVM', compute='get_tax')

    @api.one
    @api.depends('int_code')
    def get_tax(self):
        self.tax_id = self.env['account.tax'].search([('code', '=', self.int_code)], limit=1).id


GemmaVatMapper()
