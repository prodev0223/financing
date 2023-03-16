# -*- encoding: utf-8 -*-
from odoo import models, fields, api, _, exceptions


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    consignation = fields.Boolean(string='Konsignacinis produktas', track_visibility='onchange')
    consignation_location = fields.Many2one('stock.location', string='Konsignacijos nurašymo vieta',
                                            domain="[('usage', '=', 'transit')]", track_visibility='onchange')


ProductTemplate()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    consignation_picking_ids = fields.Many2many('stock.picking', relation='consignation_pickings', column1='picking1', column2='picking2', string='Konsignacijos važtaraščiai')

    @api.multi
    def action_assign(self):
        for picking in self:
            consignation_product_ids = picking.move_lines.filtered(lambda r: r.product_id.consignation)
            if consignation_product_ids:
                if picking.location_id.usage == 'internal' and picking.location_dest_id.usage == 'customer':
                    dict_key = 'location_id'
                elif (picking.location_id.usage == 'supplier' and
                      picking.location_dest_id.usage == 'internal') or (
                        picking.location_id.usage == 'customer' and picking.location_dest_id.usage == 'internal'):
                    dict_key = 'location_dest_id'
                else:
                    continue
                for location_id in consignation_product_ids.mapped('product_id.consignation_location'):
                    if not location_id:
                        raise exceptions.UserError(_('Nenurodyta konsignacijos lokacija.'))
                    new_picking_id = picking.copy()
                    picking.write({
                        'consignation_picking_ids': [(4, new_picking_id.id)]
                    })
                    new_picking_id.move_lines.filtered(lambda r: not r.product_id.consignation or r.product_id.consignation_location.id != location_id.id).unlink()
                    move_ids = new_picking_id.move_lines
                    move_ids.write({
                        dict_key: location_id.id
                    })
                    new_picking_id.write({dict_key: location_id.id})
                    new_picking_id.action_assign()
                    if new_picking_id.state == 'assigned':
                        new_picking_id.do_transfer()
                to_remove = picking.move_lines.filtered(lambda r: r.product_id.consignation and r.state != 'done')
                to_remove.do_unreserve()
                to_remove.write({'state': 'draft'})
                # Preserve the values, since min/max dates are recalculated after moves are unlinked
                vals = {'min_date': picking.min_date, 'max_date': picking.max_date, 'state': 'done'}
                to_remove.unlink()
                if not picking.move_lines:
                    picking.write(vals)
                    return True
        return super(StockPicking, self).action_assign()

    @api.multi
    def open_related_consignations(self):
        self.ensure_one()
        action = self.env.ref('robo_stock.open_robo_stock_picking').read()[0]
        action['domain'] = [('id', 'in', self.consignation_picking_ids.ids)]
        return action


StockPicking()
