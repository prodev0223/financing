# -*- coding: utf-8 -*-
from odoo import models, api


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.multi
    def _account_entry_move(self, move):
        if self._context.get('no_moves', False):
            return
        elif move.error:
            parent_move = move.origin_returned_move_id
            while parent_move.error and parent_move.origin_returned_move_id:
                parent_move = parent_move.origin_returned_move_id
            if parent_move.location_id.usage == 'production' and not \
                    parent_move.unbuild_id and not self._context.get('create_moves'):
                return
            else:
                super(StockQuant, self)._account_entry_move(move)
        elif move.location_id.usage == 'production' and not move.unbuild_id and not self._context.get('create_moves'):
            return
        elif move.location_dest_id.usage == 'production' and move.consume_unbuild_id:
            return
        else:
            super(StockQuant, self)._account_entry_move(move)

    @api.model
    def quants_get_preferred_domain(self, qty, move, ops=False, lot_id=False, domain=None, preferred_domain_list=None):
        if move.product_id.type == 'consu' and (
                not move.origin_returned_move_id and move.location_id.usage == 'internal'
                or move.origin_returned_move_id and move.location_dest_id.usage == 'internal'):
            return [(None, qty)]
        return super(StockQuant, self).quants_get_preferred_domain(
            qty, move, ops, lot_id, domain, preferred_domain_list or [])

    @api.multi
    def _search_quants_to_reconcile(self):
        # FIXME: should it use float_compare (with what precision?)
        if self.product_id.type == 'consu' and self.location_id.usage == 'internal' and self.propagated_from_id and \
                self.propagated_from_id.location_id == self.location_id and self.propagated_from_id.qty < 0.0:
            return [(self.propagated_from_id, abs(self.propagated_from_id.qty))]
        else:
            return super(StockQuant, self)._search_quants_to_reconcile()
