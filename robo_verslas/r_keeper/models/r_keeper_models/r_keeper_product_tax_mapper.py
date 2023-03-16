# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class RKeeperProductTaxMapper(models.Model):
    _name = 'r.keeper.product.tax.mapper'
    _description = '''
    Model that stores rKeeper product mappings
    with specific account tax records
    '''

    product_id = fields.Many2one('product.product', string='Produktas', inverse='_set_product_id')
    tax_id = fields.Many2one(
        'account.tax', string='Priverstiniai mokesčiai',
        domain=[('type_tax_use', '=', 'sale'), ('price_include', '=', False), ('amount', '=', 0)]
    )

    @api.multi
    @api.constrains('product_id')
    def _check_product_id(self):
        """Ensure that product is set and that only one mapper exists per product"""
        for rec in self:
            if not rec.product_id:
                raise exceptions.ValidationError(_('Privalote nurodyti produktą'))
            if self.search_count([('product_id', '=', rec.product_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Negalima turėti daugiau nei vieno mokesčių paskirstymo vienam produktui')
                )

    @api.multi
    @api.constrains('tax_id')
    def _check_tax_id(self):
        """Ensure that taxes are set"""
        for rec in self:
            if not rec.tax_id:
                raise exceptions.ValidationError(_('Privalote nurodyti produktą'))

    @api.multi
    def _set_product_id(self):
        """Recalculate taxes of all not-yet created sales"""
        sale_lines = self.env['r.keeper.sale.line'].search(
            [('invoice_id', '=', False),
             ('state', 'in', ['imported', 'failed'])]
        )
        sale_lines._compute_tax_id()
