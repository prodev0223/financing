# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, tools, exceptions, _


class MrpProductionModificationRule(models.Model):
    _name = 'mrp.production.modification.rule'

    production_id = fields.Many2one('mrp.production', string='Gamyba')

    # Information fields
    evaluation_message = fields.Char(string='Vykdymo pranešimas')
    applied = fields.Boolean(string='Pritaikyta')

    # Modification rule action fields
    application_count = fields.Integer(string='Taisyklės pritaikymo kartai')
    location_src_id = fields.Many2one('stock.location', string='Atsargų vieta')
    remove_product_id = fields.Many2one('product.product', string='Šalinamas produktas')
    add_product_id = fields.Many2one('product.product', string='Pridedamas produktas')
    action_quantity = fields.Float(string='Pridedamas kiekis')
    # Field invisible to the user, always calculated from original BOM
    action_remove_quantity = fields.Float(string='Šalinamas kiekis')
    applied_action = fields.Selection(
        [('add', 'Pridėti produktą'),
         ('remove', 'Pašalinti produktą'),
         ('swap', 'Sukeisti produktą')
         ], string='Taisyklės veiksmas',
        required=True
    )

    @api.multi
    @api.constrains('applied_action', 'action_quantity')
    def _check_action_quantity(self):
        """Ensure that action quantity is not zero on add/swap action"""
        for rec in self:
            if rec.applied_action in ['add', 'swap'] and tools.float_is_zero(
                    rec.action_quantity, precision_rounding=rec.add_product_id.uom_id.rounding or 0.003):
                raise exceptions.ValidationError(_('Privalote nurodyti pridedamą kiekį'))
            if rec.applied_action in ['remove', 'swap'] and tools.float_is_zero(
                    rec.action_remove_quantity, precision_rounding=rec.remove_product_id.uom_id.rounding or 0.003):
                raise exceptions.ValidationError(_('Privalote nurodyti šalinamą kiekį'))

    @api.multi
    @api.constrains('applied_action', 'add_product_id', 'remove_product_id')
    def _check_action_product_constraints(self):
        """Ensure that required products are set on specific action"""
        for rec in self:
            if rec.applied_action == 'swap' and (not rec.remove_product_id or not rec.add_product_id):
                raise exceptions.ValidationError(_('Privalote nurodyti pridedamą ir šalinamą produktus'))
            if rec.applied_action == 'add' and not rec.add_product_id:
                raise exceptions.ValidationError(_('Privalote nurodyti pridedamą produktą'))
            if rec.applied_action == 'remove' and not rec.remove_product_id:
                raise exceptions.ValidationError(_('Privalote nurodyti šalinamą produktą'))

    @api.multi
    def apply_modification_rule(self, factor):
        """
        Applies current modification rules to related
        production stock moves. Moves are either
        added, swapped or removed.
        :param factor: Factor amount for current
        production amount vs related BOM amount
        :return: None
        """
        # Prep a dictionary of aggregated rule moves
        aggregated_rule_moves = {}
        for rec in self:
            prod = rec.production_id
            rule_applied = True
            evaluation_message = str()
            # Calculate the final quantity: if application ratio is set use it as a multiplier,
            # otherwise production product quantity is used as an application_ratio
            multiplier = rec.application_count or prod.product_qty
            final_add_quantity = tools.float_round(
                multiplier * rec.action_quantity,
                precision_digits=5
            )
            final_remove_quantity = tools.float_round(
                multiplier * rec.action_remove_quantity,
                precision_digits=5
            )
            source_location = rec.location_src_id or prod.location_src_id
            # Search for move to be removed on remove/swap actions
            if rec.applied_action in ['remove', 'swap']:
                # Prepare grouped target move list
                grouped_target_moves = []
                total_moves = prod.move_raw_ids | prod.move_raw_ids_second
                target_moves = total_moves.filtered(lambda x: x.product_id.id == rec.remove_product_id.id)
                if target_moves:
                    grouped_target_moves.append((final_remove_quantity, target_moves, ))
                # If target moves was not found and recursive production is activated,
                # target move is likely to be exploded, in this case we check the BOM
                if not target_moves and prod.recursive_bom_production:
                    # If BOM line was found based on the product, filter out the target moves by parent BOM line
                    bom_line = prod.bom_id.bom_line_ids.filtered(
                        lambda x: x.product_id.id == rec.remove_product_id.id)
                    if bom_line:
                        # Calculate diminish factor based on the parent bom line and split the current line
                        # P3:DivOK
                        diminish_factor = factor * bom_line.product_qty / (final_remove_quantity or 1)
                        grouped_moves = bom_line.split_bom_lines(production=prod, factor=factor)
                        for move_data in grouped_moves:
                            # Loop through split moves data and gather all related
                            # moves that are in current production by product
                            inter_target_moves = total_moves.filtered(
                                lambda x: x.product_id.id == move_data['product_id']
                            )
                            if inter_target_moves:
                                # If we find any target moves, append them as potential moves
                                # to be exhausted in later calculations
                                # P3:DivOK
                                inter_remove_quantity = move_data['product_uom_qty'] / (diminish_factor or 1)
                                grouped_target_moves.append(
                                    (inter_remove_quantity, inter_target_moves, )
                                )
                if grouped_target_moves:
                    for remove_quantity, moves in grouped_target_moves:
                        # Un-reserve and delete related moves
                        moves.do_unreserve()
                        moves.action_cancel()
                        exhausted_moves = self.env['stock.move']
                        residual = remove_quantity
                        for move in moves:
                            # Residual is exhausted
                            if tools.float_is_zero(residual, precision_digits=2):
                                break
                            # Subtract the quantity from the move, if it's zero, or less
                            # remove the move and update the residual
                            subtracted_quantity = move.product_uom_qty - residual
                            if tools.float_compare(0, subtracted_quantity, precision_digits=5) >= 0:
                                exhausted_moves |= move
                                residual = abs(subtracted_quantity)
                            else:
                                move.product_uom_qty = subtracted_quantity
                                break
                        exhausted_moves.unlink()
                else:
                    evaluation_message = _('Nerastas (-i) keičiami/šalinami produktai')
                    rule_applied = False

            # We do not create the swap product move if rule was not applied
            # i.e. swap-able product was not found in the move list
            if rec.applied_action == 'swap' and not rule_applied:
                continue
            # Prepare the new stock move if action is in add or swap
            if rec.applied_action in ['add', 'swap']:
                # Check if product to add has a related bom - if it does, add product
                # is also split recursively, based on the production settings.
                # If there's no bom, we just create the move for the add product
                add_product_bom = rec.add_product_id.with_context(
                    bom_at_date=prod.date_planned_start).product_tmpl_id.bom_id
                if add_product_bom:
                    # P3:DivOK
                    factor = rec.add_product_id.uom_id._compute_quantity(
                        final_add_quantity, add_product_bom.product_uom_id) / add_product_bom.product_qty
                    stock_move_data = add_product_bom.explode_bom_recursively(production=prod, factor=factor)
                    for key, move in stock_move_data.items():
                        if key not in aggregated_rule_moves:
                            aggregated_rule_moves[key] = move
                        else:
                            aggregated_rule_moves[key]['product_uom_qty'] += move['product_uom_qty']
                else:
                    # Compose a key without an operation ID
                    key = '{}/{}/RULE-{}'.format(rec.add_product_id.id, source_location.id, rec.id)
                    if key in aggregated_rule_moves:
                        aggregated_rule_moves[key]['product_uom_qty'] += final_add_quantity
                    else:
                        move_data = {
                            'name': prod.name,
                            'date': prod.date_planned_start,
                            'date_expected': prod.date_planned_start,
                            'product_id': rec.add_product_id.id,
                            'product_uom_qty': final_add_quantity,
                            'product_uom': rec.add_product_id.uom_id.id,
                            'location_id': source_location.id,
                            'location_dest_id': prod.product_id.property_stock_production.id,
                            'raw_material_production_id': prod.id,
                            'company_id': prod.company_id.id,
                            'price_unit': rec.add_product_id.standard_price,
                            'procure_method': 'make_to_stock',
                            'origin': prod.name,
                            'warehouse_id': source_location.get_warehouse().id,
                            'group_id': prod.procurement_group_id.id,
                            'propagate': prod.propagate,
                            'production_modification_rule_id': rec.id,
                            # P3:DivOK
                            'unit_factor': final_add_quantity / rec.action_quantity if rec.action_quantity else 0,
                        }
                        aggregated_rule_moves[key] = move_data
            # Write the data to the rule
            rec.write({'applied': rule_applied, 'evaluation_message': evaluation_message})
        # Create stock moves based on aggregated data
        for move_data in aggregated_rule_moves.values():
            self.env['stock.move'].create(move_data)
