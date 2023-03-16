# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SafTTaxTable(models.Model):

    _name = 'saf.t.tax.table'
    _rec_name = 'code'

    code = fields.Char(string='Tax code')
    effective_date = fields.Date(string='Effective date')
    expiration_date = fields.Date(string='Expiration date')
    description = fields.Char(string='Description')
    percentage = fields.Float(string='Tax percentage (%)')

    @api.multi
    def name_get(self):
        result = []
        for rec in self:
            name = "[%s] %s" % (rec.code, rec.description) if rec.code else "%s" % rec.name
            result.append((rec.id, name))
        return result
