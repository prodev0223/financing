# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RKeeperProductCategory(models.Model):
    """
    TODO: FILE NOT USED AT THE MOMENT
    Model used to hold rKeeper products.
    Corresponds to product.template in our system.
    """
    _name = 'r.keeper.product.category'

    @api.model
    def _default_sale_tax(self):
        """Get default sale tax from configuration"""
        # rKeeper configuration record, never more than one
        configuration = self.env['r.keeper.configuration'].search([])
        if configuration:
            return configuration.default_sale_tax_id

    @api.model
    def _default_purchase_tax(self):
        """Get default purchase tax from configuration"""
        # rKeeper configuration record, never more than one
        configuration = self.env['r.keeper.configuration'].search([])
        if configuration:
            return configuration.default_purchase_tax_id

    ext_parent_id = fields.Integer(string='External parent ID')
    ext_id = fields.Integer(string='External ID')
    name = fields.Char(string='Name')
    code = fields.Char(string='Code')
    root_group = fields.Boolean(string='Root group category')

    # Products that belong to this category
    r_product_ids = fields.One2many('r.keeper.product')
    parent_id = fields.Many2one('r.keeper.product.category')

    sale_tax_id = fields.Many2one(
        default=_default_sale_tax,
        string='Sale tax',
        domain="[('price_include', '=', False), ('type_tax_use', '=', 'sale')]"
    )
    purchase_tax_id = fields.Many2one(
        default=_default_purchase_tax,
        string='Purchase tax',
        domain="[('price_include', '=', False), ('type_tax_use', '=', 'purchase')]"
    )

