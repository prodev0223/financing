# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, fields, tools, _


class StockMove(models.Model):
    _inherit = 'stock.move'

    invoice_line_id = fields.Many2one('account.invoice.line', inverse='_inverse_invoice_line_id')
    total_move_amount = fields.Float(
        string='Planuojama savikaina',
        compute='_compute_total_move_amount'
    )
    price_unit_forced = fields.Float(
        string='Vnt. kaina',
        compute='_compute_price_unit_forced',
        inverse='_set_price_unit_forced',
    )

    quants_to_date = fields.Char(
        string='Panaudojamas (Turimas) kiekis', compute='_compute_quantities_to_date',
        help='Skliausteliuose atvaizduojamas realus atsargų kiekis sandelyje, '
             'kitas skaičius rodo nerezervuotų/panaudojamų atsargų kiekį'
    )
    quants_to_date_real = fields.Float(compute='_compute_quantities_to_date')
    insufficient_stock = fields.Boolean(compute='_compute_quantities_to_date')
    product_qty_real = fields.Float(string='Quantity change', compute='_compute_product_qty_real')

    @api.multi
    def _inverse_invoice_line_id(self):
        for rec in self.filtered(lambda m: m.invoice_line_id and not m.origin):
            invoice = rec.invoice_line_id.invoice_id
            if invoice:
                rec.origin = invoice.reference if invoice.type in ['in_invoice', 'in_refund'] else invoice.number

    @api.multi
    @api.depends('date_expected', 'location_id', 'product_id', 'product_uom_qty', 'quantity_available')
    def _compute_quantities_to_date(self):
        """
        Compute product quantities to date,
        usable quantity and all available,
        including reserved stock moves
        :return: None
        """
        for rec in self.filtered(lambda x: x.product_id):
            quantities = rec.product_id.get_product_quantities(
                location=rec.location_id
            )
            rec.quants_to_date = quantities['display_quantity']
            rec.quants_to_date_real = quantities['usable_quantity']

            # Check if we have insufficient stock
            insufficient_stock = tools.float_compare(
                rec.product_uom_qty, quantities['usable_quantity'],
                precision_rounding=rec.product_uom.rounding or 0.01
            ) > 0
            rec.insufficient_stock = insufficient_stock

    @api.multi
    @api.depends('product_uom_qty', 'price_unit_forced', 'state', 'non_error_quant_ids')
    def _compute_total_move_amount(self):
        """Calculate total move amount - price unit * quantity"""
        for rec in self:
            total_amount = rec.product_uom_qty * rec.price_unit_forced
            if tools.float_is_zero(total_amount, precision_digits=2):
                total_amount = rec.product_id.avg_cost * rec.product_uom_qty
            rec.total_move_amount = total_amount

    @api.multi
    @api.depends('price_unit')
    def _compute_price_unit_forced(self):
        """Calculate forced price unit based on product type and quants"""
        for rec in self:
            if rec.product_id.type == 'consu':
                rec.price_unit_forced = rec.price_unit
            elif rec.quant_ids:
                # P3:DivOK
                rec.price_unit_forced = sum(r.cost * r.qty for r in rec.quant_ids) / sum(rec.quant_ids.mapped('qty'))
            elif rec.reserved_quant_ids:
                rec.price_unit_forced = sum(r.cost * r.qty for r in rec.reserved_quant_ids) / sum(
                    rec.reserved_quant_ids.mapped('qty'))  # P3:DivOK

    @api.multi
    @api.depends('product_qty')
    def _compute_product_qty_real(self):
        for rec in self:
            source_loc_usage = rec.location_id.usage
            destination_loc_usage = rec.location_dest_id.usage
            is_negative = True
            if source_loc_usage == 'internal' and destination_loc_usage != 'internal':
                is_negative = True
            elif source_loc_usage != 'internal' and destination_loc_usage == 'internal':
                is_negative = False
            rec.product_qty_real = -rec.product_qty if is_negative else rec.product_qty

    @api.multi
    def _set_price_unit_forced(self):
        """Set forced price unit on consumable products"""
        for rec in self.filtered(lambda x: x.product_id.type == 'consu'):
            rec.price_unit = rec.price_unit_forced
