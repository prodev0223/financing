# -*- coding: utf-8 -*-
import re
from odoo import fields, models, api, _, exceptions


class ResBank(models.Model):
    _inherit = 'res.bank'

    kodas = fields.Char(string='Banko kodas', required=True)

    _sql_constraints = [('unique_bank_code', 'unique (kodas)', _('Bank code must be unique'))]

    @api.onchange('kodas')
    def onchange_kodas_strip(self):
        if self.kodas:
            self.kodas = self.kodas.strip()

    @api.onchange('bic')
    def onchange_bic_strip(self):
        if self.bic:
            self.bic = self.bic.strip()

    @api.multi
    @api.constrains('bic')
    def constrains_bic(self):
        bic_pattern = re.compile('^([A-Z]{6}[A-Z2-9][A-NP-Z1-9])(X{3}|[A-WY-Z0-9][A-Z0-9]{2})?$')
        for rec in self:
            if rec.bic and not bic_pattern.match(rec.bic):
                raise exceptions.ValidationError(_('BIC kodas neatitinka formato!'))
