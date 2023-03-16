# -*- coding: utf-8 -*-
from __future__ import division
import logging
from datetime import datetime
from odoo import models, fields, api, tools, exceptions, _


_logger = logging.getLogger(__name__)


class QuantImportTable(models.Model):

    _name = 'quant.import.table'

    product_id = fields.Many2one('product.product', string='Produktas', required=True)
    location_id = fields.Many2one('stock.location', string='Lokacija', required=True)
    serial_number = fields.Char(string='SN')
    package = fields.Char(string='Pakuotė')
    state = fields.Selection([('not_import', 'Not imported'),
                              ('import', 'Imported'),
                              ('error', 'General Error'),
                              ('error_lot', 'Error Lot'),
                              ('error_no_quant', 'Error No quant'),
                              ('error_qty', 'Error qty')],
                             string='Statusas', default='not_import', required=True)
    qty = fields.Float(string='Kiekis')
    in_date = fields.Date(string='Priėmimo data')
    total_cost_theoretical = fields.Float(string='Vertė')
    cost_computed = fields.Float(string='Suskaičiuota vertė', compute='_cost_computed', store=True)
    qty_done = fields.Float(string='Perkeltas kiekis')
    move_id = fields.Many2one('stock.move', string='Created stock move', readonly=True)
    package_id = fields.Many2one('stock.quant.package', string='Created package', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', string='Created SN', readonly=True)

    @api.multi
    def add_qtys(self):
        if not self.env.user._is_admin():
            return
        # goal_data = self.env['quant.import.table'].search([('state', '!=', 'import')])
        inventory_loc = self.env.ref('stock.location_inventory').id
        for rec in self:
            if rec.state == 'import':
                continue
            date = datetime.strptime(rec.in_date, tools.DEFAULT_SERVER_DATE_FORMAT).strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT)
            stock_move_vals = {'product_id': rec.product_id.id,
                               'product_uom': rec.product_id.uom_id.id,
                               'product_uom_qty': rec.qty,
                               'date': date,
                               'date_expected': date,
                               'location_id': inventory_loc,  # opposite
                               'location_dest_id': rec.location_id.id,
                               'name': '/',
                               }

            stock_move = self.env['stock.move'].create(stock_move_vals)
            stock_move.action_assign()
            stock_move.with_context(no_moves=True, no_raise=True).action_done()
            stock_move.write({'date': date})
            package = False
            if rec.package:
                package = self.env['stock.quant.package'].search([('name', '=', rec.package)], limit=1)
                if not package:
                    package = self.env['stock.quant.package'].create({'name': rec.package})
                    rec.write({'package_id': package.id})
            quants = stock_move.quant_ids
            if package:
                quants.write({'package_id': package.id})
            if rec.serial_number:
                if len(quants) != 1:
                    raise exceptions.Warning(_('Sistemos klaida. Kreipkitės į administratorius.'))
                lot = self.env['stock.production.lot'].search(
                    [('product_id', '=', rec.product_id.id), ('name', '=', rec.serial_number)], limit=1)
                if not lot:
                    lot = self.env['stock.production.lot'].create({'name': rec.serial_number,
                                                                   'product_id': rec.product_id.id})
                    rec.write({'lot_id': lot.id})
                if lot.quant_ids:
                    raise exceptions.Warning(_('Serijos numeris %s jau priskirtas.') % lot.name)
                quants.write({'lot_id': lot.id})
            rec.write({
                'state': 'import',
                'move_id': stock_move.id,
            })
            quants.write({'in_date': rec.in_date, 'cost': rec.cost_computed})

    @api.one
    @api.depends('total_cost_theoretical', 'qty')
    def _cost_computed(self):
        if self.qty > 0 and self.total_cost_theoretical > 0:
            self.cost_computed = self.total_cost_theoretical / self.qty  # P3:DivOK
        else:
            self.cost_computed = 0
