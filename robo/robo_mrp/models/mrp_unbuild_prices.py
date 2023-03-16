# -*- coding: utf-8 -*-
from odoo import models, api, fields
from odoo.addons import decimal_precision as dp


class MrpUnbuildPrices(models.Model):
    _name = 'mrp.unbuild.prices'

    @api.model
    def _price_unit_precision(self):
        """Get precision for price unit"""
        return max((16, 4), dp.get_precision('Product Price'))

    unbuild_id = fields.Many2one('mrp.unbuild', readonly=True)
    product_id = fields.Many2one('product.product', string='Produktas', readonly=True)
    qty = fields.Float(string='Kiekis', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    price_unit = fields.Float(string='Vnt. savikaina', digits=_price_unit_precision)
    total_value = fields.Float(string='Suma', compute='_compute_total_value')
    let_modify = fields.Boolean(compute='_compute_let_modify')

    @api.multi
    def _compute_let_modify(self):
        """
        Check whether stock moves can be
        edited in the form view based on the
        mrp type in company settings
        :return: None
        """
        company = self.sudo().env.user.company_id
        for rec in self:
            rec.let_modify = company.mrp_type == 'dynamic'

    @api.multi
    @api.depends('qty', 'price_unit')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = (rec.qty or 0.0) * (rec.price_unit or 0.0)
