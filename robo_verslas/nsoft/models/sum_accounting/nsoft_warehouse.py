# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class NSoftWarehouse(models.Model):

    _name = 'nsoft.warehouse'
    _description = '''Model that nSoft warehouse data, used for analytic mapping'''

    name = fields.Char(string='Pavadinimas', required=True)
    code = fields.Char(string='Kodas', required=True)

    # Analytic account
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        domain="[('account_type', 'in', ['expense', 'profit'])]",
        string='Numatytoji analitinė sąskaita'
    )

    @api.constrains('code')
    def _check_warehouse_code(self):
        """Ensure that there aren't any duplicate warehouses using it's code"""
        for rec in self:
            if self.search_count([('code', '=', rec.code)]) > 1:
                raise exceptions.ValidationError(
                    _('Negalite turėti dviejų nSoft sandėlių su tuo pačiu kodu')
                )

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, '[{}] {}'.format(rec.code, rec.name)) for rec in self]
