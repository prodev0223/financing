# -*- coding: utf-8 -*-
from __future__ import division
from odoo import api, models, _, exceptions


class ChangeProductionQty(models.TransientModel):
    _inherit = 'change.production.qty'

    @api.multi
    def change_prod_qty(self):
        for wizard in self:
            if wizard.mo_id.state in ['done', 'cancel']:
                raise exceptions.UserError(
                    _('Jūs negalite pakeisti kiekio, kadangi gamyba yra atlikta arba yra atšaukta'))

        # Do not update dynamic productions or productions that have recursive exploded moves
        spec_recs = self.filtered(
            lambda w: w.mo_id.production_type == 'dynamic' or
            w.mo_id.recursive_bom_production_mode in ['explode_all', 'explode_no_stock'] or
            w.mo_id.modification_rule_production
        )
        other_recs = self.filtered(lambda x: x.id not in spec_recs.ids)
        super(ChangeProductionQty, other_recs).change_prod_qty()
        # Loop through wizard records that are have either dynamic or recursive productions
        for wizard in spec_recs:
            production = wizard.mo_id
            produced = sum(production.move_finished_ids.mapped('quantity_done'))
            if wizard.product_qty < produced:
                raise exceptions.UserError(
                    _('Jūs jau esate pagaminę %d. Prašome panaudoti didesnį kiekį nei %d') % (produced, produced))
            # Update finished moves with current quantity
            self._update_product_to_produce(production, wizard.product_qty - produced)
            if production.production_type == 'dynamic':
                # P3:DivOK
                factor = wizard.product_qty / production.product_qty
                production.write({'product_qty': wizard.product_qty,
                                  'move_raw_ids': [(1, line.id, {'product_uom_qty': line.product_uom_qty * factor})
                                                   for line in production.move_raw_ids]})
                moves = production.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
                moves.do_unreserve()
                moves.action_assign()

            # If production is recursive, unlink and recreate the moves
            # This is done due to aggregation with different unit factor
            elif production.recursive_bom_production_mode in ['explode_all', 'explode_no_stock']:
                moves = production.move_raw_ids
                if any(x.state in ['done', 'cancel'] for x in moves):
                    raise exceptions.UserError(
                        _('Negalite pakeisti kiekio, bent vienas gamybos komponentas yra atšauktas arba pagamintas')
                    )

                production.write({'product_qty': wizard.product_qty})
                # Recreate raw moves for the production
                production.recreate_raw_moves()
