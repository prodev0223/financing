# -*- coding: utf-8 -*-
from odoo import models, fields, api
import odoo.addons.decimal_precision as dp


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    qty_in_stock = fields.Float(string='Atsargos sandėlyje', compute='_qty_in_stock',
                                digits=dp.get_precision('Product Unit of Measure'))
    avg_cost = fields.Float(string='Savikaina', compute='_avg_cost', groups='robo_stock.group_show_avg_cost')
    lot_ids = fields.Many2many('stock.production.lot', string='SN', compute='_lot_ids')
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', readonly=True)

    required_location_id = fields.Boolean(compute='_compute_required_location_id')
    location_id = fields.Many2one(
        'stock.location', string='Atsargų vieta',
        domain="[('usage','=','internal')]",
    )

    @api.multi
    @api.depends('product_id')
    def _compute_required_location_id(self):
        """
        Compute //
        Check whether location field in the invoice line
        should be required or not
        :return: None
        """
        has_group = self.env.user.has_group('robo_stock.group_simplified_stock_multi_locations')
        for rec in self:
            rec.required_location_id = rec.product_id.type == 'product' and has_group

    @api.multi
    @api.depends('product_id', 'location_id')
    def _qty_in_stock(self):
        """
        Compute //
        Get quantity in stock, if location
        is set on invoice line, filter
        quantities for that location
        :return: None
        """
        has_group = self.env.user.has_group('robo_stock.group_simplified_stock_multi_locations')
        for rec in self:
            quantity = 0.0
            if rec.product_id:
                if has_group and rec.location_id:
                    quantity = rec.product_id.with_context(location_id=rec.location_id.id).qty_available
                else:
                    quantity = rec.product_id.qty_available
            rec.qty_in_stock = quantity

    @api.one
    @api.depends('product_id')
    def _avg_cost(self):
        if self.product_id and self.product_id.type == 'product':
            all_quants = self.sudo().env['stock.quant'].search(
                [('product_id', '=', self.product_id.id), ('location_id.usage', '=', 'internal')])
            all_cost = sum(all_quants.mapped(lambda r: r.qty * r.cost))
            all_qty = sum(all_quants.mapped('qty'))
            if all_qty:
                self.avg_cost = all_cost / all_qty
        elif self.product_id:
            self.avg_cost = self.product_id.standard_price

    @api.one
    @api.depends('sale_line_ids.qty_delivered', 'invoice_id.picking_id.move_lines.state')
    def _lot_ids(self):
        product_id = self.product_id.id if self.product_id else False
        if product_id:
            if self.sudo().sale_line_ids:
                self.lot_ids = self.sudo().sale_line_ids.mapped('procurement_ids.move_ids').filtered(
                    lambda r: r.product_id.id == product_id and r.state == 'done'
                    and r.location_dest_id.usage == 'customer' and not r.returned_move_ids.filtered(
                        lambda x: x.error and x.state == 'done')
                ).mapped('quant_ids.lot_id').sorted(lambda r: r.name).ids
            elif self.sudo().invoice_id.picking_id:
                self.lot_ids = self.sudo().invoice_id.picking_id.move_lines.filtered(
                    lambda r: r.product_id.id == product_id and r.state == 'done'
                    and r.location_dest_id.usage == 'customer' and not r.returned_move_ids.filtered(
                        lambda x: x.error and x.state == 'done')
                ).mapped('quant_ids.lot_id').sorted(lambda r: r.name).ids
        if not self.lot_ids and self.sudo().sale_line_ids:
            self.lot_ids = self.sudo().sale_line_ids.mapped(
                'procurement_ids.move_ids.picking_id.pack_operation_product_ids').filtered(
                lambda r: r.product_id.id == product_id).filtered(
                lambda r: r.qty_done > 0).mapped('pack_lot_ids').filtered(lambda r: r.qty > 0).mapped('lot_id').sorted(
                lambda r: r.name).ids

    @api.onchange('product_id')
    def onchange_product_id(self):
        """Onchange -- On product change, apply the locations"""
        if self.product_id.type == 'product':
            self.location_id = self.invoice_id.location_id
        else:
            self.location_id = False
