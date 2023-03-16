# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    cost = fields.Float(digits=(16, 16))

    @api.multi
    def name_get(self):
        return [(rec.id, _('Quant') + ' #' + str(rec.id)) for rec in self]

    @api.model
    def quants_get_preferred_domain(self, qty, move, ops=False, lot_id=False, domain=None, preferred_domain_list=None):
        if self._context.get('return_use_quants'):
            quants_to_use = []
            for t in self._context.get('return_use_quants'):
                if t and len(t) > 0 and t[0].product_id.id == move.product_id.id:
                    quants_to_use.append(t)
            return quants_to_use
        if self._context.get('origin_quant_ids'):
            domain += [('id', 'in', self._context.get('origin_quant_ids'))]
        return super(StockQuant, self).quants_get_preferred_domain(qty, move, ops, lot_id,
                                                                   domain, preferred_domain_list or [])
