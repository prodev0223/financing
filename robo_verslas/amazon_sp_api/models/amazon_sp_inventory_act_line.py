# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AmazonSPInventoryActLine(models.Model):
    _name = 'amazon.sp.inventory.act.line'
    _description = _('Model that is used to hold data about Amazon SP inventory act lines')

    amazon_inventory_id = fields.Many2one(
        'amazon.sp.inventory.act', string='Inventory act',
        required=True, ondelete='cascade',
    )
    amazon_product_id = fields.Many2one(
        'amazon.sp.product', string='Related product'
    )
    asin_product_code = fields.Char(string='Related product asin', inverse='_set_asin_product_code')
    write_off_quantity = fields.Float(string='Write-off quantity')

    @api.multi
    def _set_asin_product_code(self):
        """Relate amazon product to inventory line using ASIN code"""
        AmazonSPProduct = self.env['amazon.sp.product'].sudo()
        for rec in self.filtered('asin_product_code'):
            rec.amazon_product_id = AmazonSPProduct.search([('asin_product_code', '=', rec.asin_product_code)])
