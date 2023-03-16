# -*- coding: utf-8 -*-
from odoo import models, api, _, fields, tools, exceptions
from odoo.tools import float_compare, float_round
from odoo.exceptions import UserError
from datetime import datetime


class ChangeProductionLocation(models.TransientModel):
    _name = 'change.production.location'
    _description = 'Change Location of Products in Production'

    mo_id = fields.Many2one('mrp.production', 'Manufacturing Order', required=True)
    location_src_id = fields.Many2one('stock.location', string='Žaliavų vieta', domain=[('usage', '=', 'internal')])
    location_dest_id = fields.Many2one('stock.location', string='Gaminių vieta', domain=[('usage', '=', 'internal')])

    @api.model
    def default_get(self, fields):
        res = super(ChangeProductionLocation, self).default_get(fields)
        if 'mo_id' in fields and not res.get('mo_id') and self._context.get(
                'active_model') == 'mrp.production' and self._context.get('active_id'):
            res['mo_id'] = self._context['active_id']
        if 'location_src_id' in fields and not res.get('product_qty') and res.get('mo_id'):
            res['location_src_id'] = self.env['mrp.production'].browse(res['mo_id']).location_src_id.id
        if 'location_dest_id' in fields and not res.get('product_qty') and res.get('mo_id'):
            res['location_dest_id'] = self.env['mrp.production'].browse(res['mo_id']).location_dest_id.id
        return res

    @api.multi
    def change_production_location_dest_id(self):
        self.ensure_one()
        if self.mo_id.state not in ['confirmed', 'planned']:
            raise exceptions.UserError(_('Nebegalite pakeisti gamybos gaminių vietos, nes gamyba jau yra pradėta'))
        moves = self.mo_id.move_finished_ids
        moves.write({'location_dest_id': self.location_dest_id.id})
        self.mo_id.write({'location_dest_id': self.location_dest_id.id})

    @api.multi
    def change_production_location_src_id(self):
        self.ensure_one()
        if self.mo_id.state not in ['confirmed', 'planned']:
            raise exceptions.UserError(_('Nebegalite pakeisti gamybos žaliavų vietos, nes gamyba jau yra pradėta'))
        moves = self.mo_id.move_raw_ids
        moves.do_unreserve()
        moves.write({'location_id': self.location_src_id.id})
        values_to_write = {
            'location_src_id': self.location_src_id.id
        }
        picking_type_id = self.env['stock.picking.type'].search([
            ('code', '=', 'mrp_operation'), ('default_location_src_id', '=', self.location_src_id.id)], limit=1).id
        if picking_type_id:
            values_to_write.update({
                'picking_type_id': picking_type_id
            })
        self.mo_id.write(values_to_write)
        moves.action_assign()

    @api.multi
    def change_prod_location(self):
        for wizard in self:
            production = wizard.mo_id
            if wizard.location_dest_id != production.location_dest_id:
                wizard.change_production_location_dest_id()
            if wizard.location_src_id != production.location_src_id:
                wizard.change_production_location_src_id()
        return {}
