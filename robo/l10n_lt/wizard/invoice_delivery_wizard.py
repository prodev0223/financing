# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime
from six import iteritems


class InvoiceDeliveryWizard(models.TransientModel):
    _name = 'invoice.delivery.wizard'

    def _delivery_date(self):
        if self._context.get('invoice_id', False):
            invoice = self.env['account.invoice'].browse(self._context.get('invoice_id', False))
            return invoice.date_invoice
        return datetime.utcnow()

    def _invoice_id(self):
        if self._context.get('invoice_id', False):
            return self._context['invoice_id']

    def _origin_picking_ids(self):
        invoice_id = self._context.get('invoice_id', False)
        res = []
        if invoice_id:
            invoice = self.env['account.invoice'].browse([invoice_id])[0]
        else:
            invoice = None
        if invoice:
            res += [(4, picking_id,) for picking_id in invoice._get_origin_picking_ids()]
        return res

    location_id = fields.Many2one('stock.location', string='Location', required=True,
                                  domain="[('usage','=','internal')]")
    delivery_date = fields.Date(string='Delivery Date', default=_delivery_date, required=True)
    invoice_id = fields.Many2one('account.invoice', string='Invoice', default=_invoice_id)
    origin_picking_ids = fields.Many2many('stock.picking', string='Grąžinami važtaraščiai',
                                          default=_origin_picking_ids)
    select_origin_picking = fields.Boolean(string='Pasirinkti grąžinimus rankiniu būdu', default=False)
    is_out_refund = fields.Boolean(compute="_is_out_refund", string='Ar kreditinė sąskaita?')

    @api.one
    @api.depends('invoice_id')
    def _is_out_refund(self):
        if self.invoice_id and self.invoice_id.type == 'out_refund':
            self.is_out_refund = True

    @api.one
    def _get_origin_picking_ids(self):
        if self.invoice_id and self.invoice_id.origin:
            self.origin_picking_ids = [(5,)] + [(4, p,) for p in self.invoice_id._get_origin_picking_ids()]

    @api.multi
    def prepare_data_by_location(self):
        """
        Groups data by location.
        Method meant to be overridden
        :return: grouped data (dict)
        """
        lines_by_location = {self.location_id: self.invoice_id.invoice_line_ids}
        return lines_by_location

    @api.multi
    def get_move_vals(self, invoice_line, picking):
        self.ensure_one()
        return {
            'product_id': invoice_line.product_id.id,
            'date': self.delivery_date,
            'date_expected': self.delivery_date,
            'product_uom': invoice_line.product_id.uom_id.id or self.env.ref('product.product_uom_unit').id,
            'product_uom_qty': invoice_line.quantity,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'name': invoice_line.product_id.name,
            'invoice_line_id': invoice_line.id,
            'state': 'confirmed',
        }

    @api.multi
    def create_delivery(self):
        self.ensure_one()
        if not self.invoice_id:
            raise exceptions.UserError(_('Nepavyko nustatyti sąskaitos.'))
        partner = self.invoice_id.partner_id
        invoice_type = self.invoice_id.type
        warehouse = self.location_id.warehouse_id
        if not warehouse:
            raise exceptions.UserError(_('Nepavyko nustatyti sandėlio atsargų vietai - %s.') % self.location_id.name)
        if not self.invoice_id.invoice_line_ids.filtered(lambda r: r.product_id.type == 'product'):
            return {'type': 'ir.actions.act_window_close'}
        pick_type_id = warehouse.in_type_id if self.invoice_id.type in ['in_invoice',
                                                                        'out_refund'] else warehouse.out_type_id
        if self.is_out_refund and not self.select_origin_picking:
            self._get_origin_picking_ids()

        shipping_type = 'transfer'
        # One location is determined based on invoice type,
        # other one is taken from the invoice lines
        s_location = d_location = None
        if invoice_type == 'in_invoice':
            s_location = partner.property_stock_supplier
        elif invoice_type == 'out_invoice':
            d_location = partner.property_stock_customer
        elif invoice_type == 'out_refund':
            s_location = partner.property_stock_customer
            shipping_type = 'return'
        elif invoice_type == 'in_refund':
            d_location = self.invoice_id.partner_id.property_stock_supplier
        else:
            raise exceptions.UserError(_('Netinkamas sąskaitos tipas'))

        created_pickings = self.env['stock.picking']
        lines_by_location = self.prepare_data_by_location()
        # Loop through the locations, and create pickings
        for location, inv_lines in iteritems(lines_by_location):
            # Set the other location, one is taken from the iterator,
            # other is set based on the invoice type
            destination = d_location if d_location else location
            source = location if d_location else s_location

            vals = {
                'picking_type_id': pick_type_id.id,
                'partner_id': self.invoice_id.partner_id.id,
                'date': self.delivery_date,
                'origin': self.invoice_id.number,
                'location_dest_id': destination.id,
                'location_id': source.id,
                'company_id': self.invoice_id.company_id.id,
                'shipping_type': shipping_type,
                'select_origin_picking': self.select_origin_picking,
            }
            picking = self.env['stock.picking'].create(vals)
            s_move_lines = []
            for line in inv_lines.filtered(lambda x: x.product_id.type == 'product'):
                move_val = self.get_move_vals(line, picking)
                if self.invoice_id.type in ('in_invoice',):
                    price_unit = 0.0
                    if not tools.float_is_zero(line.quantity, precision_digits=2):
                        # P3:DivOK - both fields are float
                        price_unit = line.price_subtotal_signed / line.quantity
                    move_val['price_unit'] = price_unit
                s_move_lines.append((0, 0, move_val))
            if s_move_lines:
                picking.write({'move_lines': s_move_lines, 'state': 'confirmed'})
                # Only the first picking is assigned to the invoice
                # other pickings will be find via the origin field
                if not self.invoice_id.picking_id:
                    self.invoice_id.picking_id = picking.id
                if self.is_out_refund and self.select_origin_picking and self.origin_picking_ids:
                    picking.origin_picking_ids = [(6, 0, self.origin_picking_ids.ids)]
                    picking.update_quants_to_return()
                created_pickings |= picking
            else:
                picking.unlink()

        # Relate newly created pickings to landed costs
        if self.invoice_id.landed_cost_ids and created_pickings:
            self.invoice_id.landed_cost_ids.write({
                'picking_ids': [(4, pick.id) for pick in created_pickings],
            })

