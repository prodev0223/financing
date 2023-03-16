# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class EbayCurrencyMapper(models.Model):
    _name = 'ebay.currency.mapper'
    _description = _('Model that is used to map custom ebay currency string to internal currency record')

    external_code = fields.Char(string='External currency code', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)

    @api.multi
    @api.constrains('external_code')
    def _check_external_code(self):
        """Ensure that external code is unique"""
        for rec in self:
            if self.search_count([('external_code', '=', rec.external_code)]) > 1:
                raise exceptions.ValidationError(
                    _('External code {} already has a mapping!').format(rec.external_code)
                )

    @api.multi
    def name_get(self):
        """Custom name get for mapper"""
        return [
            (x.id, _('[%s] -> [%s]') % (x.external_code, x.currency_id.name)) for x in self
        ]
