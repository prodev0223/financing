# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SafTAccount(models.Model):

    _name = 'saf.t.account'
    _rec_name = 'code'

    code = fields.Char(string='Account code')
    description = fields.Char(string='Description')

    @api.multi
    def name_get(self):
        result = []
        for rec in self:
            name = "%s %s" % (rec.code, rec.description) if rec.code else "%s" % rec.name
            result.append((rec.id, name))
        return result
