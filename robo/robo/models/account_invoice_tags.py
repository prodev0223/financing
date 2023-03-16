# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class AccountInvoiceTags(models.Model):
    _name = 'account.invoice.tags'

    name = fields.Char(string='Pavadinimas', required=True)
    code = fields.Char(string='Kodas', required=True)
    color = fields.Char(string='Spalva', required=True)
    description = fields.Char(string='Aprašymas')

    @api.multi
    @api.constrains('code')
    def constraint_name(self):
        for rec in self:
            if rec.search([('code', '=', rec.code)], count=True) > 1:
                raise exceptions.ValidationError(_('Žymų pavadinimai negali kartotis.'))
