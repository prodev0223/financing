# -*- coding: utf-8 -*-

from odoo import models, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.onchange('product_uom_qty')
    def _onchange_date_planned_start(self):
        """
        Return default domain to stock move product_id field,
        by filtering out any POS products.
        """
        # Methods ensure that no more than one configuration exists
        return {'domain': {'product_id': [('r_keeper_pos_filter', '=', False)]}}
