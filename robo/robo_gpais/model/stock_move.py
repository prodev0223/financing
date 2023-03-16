# -*- coding: utf-8 -*-
from odoo import  api, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.multi
    def guess_gpais_supply_type(self):
        """We try to guess the GPAIS supply type from the quant movements. Returns False if could not guess."""
        self.ensure_one()
        supply_type = False
        if self.quant_ids:
            quant_id = self.quant_ids[0]
            moves = quant_id.non_error_history_ids.filtered(lambda m: m.date <= self.date and
                                                                      m.location_dest_id.usage == 'internal')
            reverse = True if quant_id.product_id.product_tmpl_id.gpais_product_type == 'prekinisVienetas' else False
            for history_move in moves.sorted(key=lambda r: r.date, reverse=reverse):
                if history_move.location_id.usage == 'production':
                    supply_type = 'production'
                    break
                elif history_move.location_id.usage == 'supplier':
                    supply_type = 'supplier'
                    break
                # Reverse supply type is not used for now, if set, it should be skipped in journal
                elif history_move.location_id.usage == 'customer':
                    supply_type = 'reverse'
                    break
        return supply_type
