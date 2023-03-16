# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.tools import float_compare


class StockQuantReturn(models.Model):
    _name = 'stock.quant.return'

    quant_id = fields.Many2one('stock.quant', string='Prekių kiekis')
    picking_id = fields.Many2one('stock.picking', string='Važtaraštis', ondelete='cascade')
    cost = fields.Float(compute='get_quant_vals', string='Vertė')
    product_id = fields.Many2one('product.product', compute='get_quant_vals', string='Produktas')
    in_date = fields.Datetime(compute='get_quant_vals', string='Gavimo Data')
    qty = fields.Float(compute='get_quant_vals', string='Kiekis')
    qty_to_return = fields.Float(default=0.0, string='Grąžinamas kiekis')

    @api.one
    @api.depends('quant_id')
    def get_quant_vals(self):
        if self.quant_id:
            self.cost = self.quant_id.inventory_value
            self.in_date = self.quant_id.in_date
            self.qty = self.quant_id.qty
            self.product_id = self.quant_id.product_id

    @api.multi
    def update_quantities(self):
        for rec in self:
            rec.qty = rec.quant_id.qty
            if float_compare(rec.qty_to_return, rec.qty, precision_digits=4) > 0:
                rec.qty_to_return = rec.qty

    @api.constrains('qty_to_return')
    def constr_qty_to_return(self):
        for rec in self:
            if float_compare(rec.qty_to_return, rec.qty, precision_digits=4) > 0:
                raise exceptions.ValidationError(_('Negalima grąžinti daugiau nei partijos kiekis.'))
