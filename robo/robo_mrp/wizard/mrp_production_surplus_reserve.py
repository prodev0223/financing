# -*- coding: utf-8 -*-
from odoo import models, api, fields, tools


class MrpProductionSurplusReserve(models.TransientModel):
    _name = 'mrp.production.surplus.reserve'

    production_id = fields.Many2one('mrp.production')

    @api.multi
    def process(self):
        self.ensure_one()
        inventory_loc_id = self.env.ref('stock.location_inventory').id
        production = self.production_id

        # We can't do surplus action_assign outside the wizard - action assign
        # with skip_stock_availability_check reserves the moves that it can, however,
        # if user just closes the wizard, moves are left in reserved state, and that
        # does not preserve previous behaviour, where all moves are roll-backed to
        # draft if at least one of them failed the reservation.
        production.with_context(skip_stock_availability_check=True).action_assign()
        surplus_moves = production.get_failed_to_reserve_moves()

        # If we do not find any surplus moves (insufficient_stock check can change in the meantime),
        # just return - all moves were reserved with the previous action
        if not surplus_moves:
            return

        # Group moves by destination location - it's either production or move's source
        by_location = {}
        for surplus_move in surplus_moves:
            destination = surplus_move.location_id.id or production.location_src_id.id
            by_location.setdefault(destination, self.env['stock.move'])
            by_location[destination] |= surplus_move

        # Create multiple pickings per destination location
        for d_location, moves_by_loc in by_location.items():
            picking_vals = {
                'picking_type_id': self.env.ref('stock.picking_type_internal').id,
                'date': production.accounting_date,
                'origin': production.name,
                'location_id': inventory_loc_id,
                'location_dest_id': d_location,
                'shipping_type': 'transfer',
            }
            picking = self.env['stock.picking'].create(picking_vals)
            lines = []

            for surplus_move in moves_by_loc:
                qty = tools.float_round(
                    surplus_move.product_uom_qty - surplus_move.quantity_available,
                    precision_rounding=surplus_move.product_uom.rounding or 0.01
                )
                stock_move_vals = {
                    'product_id': surplus_move.product_id.id,
                    'product_uom': surplus_move.product_uom.id,
                    'product_uom_qty': qty,
                    'date': production.accounting_date,
                    'date_expected': production.accounting_date,
                    'location_id': inventory_loc_id,
                    'location_dest_id': d_location,
                    'name': production.name,
                    'surplus_production_id': production.id,
                }
                lines.append((0, 0, stock_move_vals))

            picking.move_lines = lines
            picking.action_assign()
            if picking.state == 'assigned':
                picking.do_transfer()
        production.action_assign()
