# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class StockMove(models.Model):
    _inherit = 'stock.move'

    secondary_uom_id = fields.Many2one('product.uom', string='Antrinis matavimo vienetas',
                                       inverse='_set_product_qty_from_secondary')
    secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais',
                                     inverse='_set_product_qty_from_secondary')
    secondary_uom_domain = fields.Many2many('product.uom', string='Leidžiami matavimo vienetai',
                                            compute='_secondary_uom_domain')

    @api.one
    @api.depends('product_id')
    def _secondary_uom_domain(self):
        # called regularly and from onchange
        self.secondary_uom_domain = (self.product_id.product_uom_lines.mapped('uom_id') | self.product_id.uom_id).ids

    def compute_main_product_qty(self):
        # called regularly and from onchange

        if self.secondary_uom_id and self.product_uom and self.product_id:
            self.product_uom_qty = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                              self.secondary_uom_id,
                                                                                              self.product_uom)
        elif not self.secondary_uom_id and self.product_uom and not tools.float_is_zero(self.secondary_uom_qty,
                                                                                        precision_rounding=self.product_uom.rounding):
            self.product_uom_qty = self.secondary_uom_qty

    @api.one
    def _set_product_qty_from_secondary(self):
        # even if there is no
        self.compute_main_product_qty()

    @api.onchange('product_id', 'secondary_uom_id', 'secondary_uom_qty')
    def onch_secondary_uom_id(self):
        self.compute_main_product_qty()

    @api.model
    def create(self, vals):
        if vals.get('procurement_id') and 'secondary_uom_id' not in vals:
            procurement = self.env['procurement.order'].browse(vals.get('procurement_id'))
            sale_line = procurement.sale_line_id
            if sale_line:
                vals.update({'secondary_uom_id': sale_line.secondary_uom_id.id,
                             'secondary_uom_qty': sale_line.secondary_uom_qty})
        if vals.get('purchase_line_id') and 'secondary_uom_id' not in vals:
            purchase_line = self.env['purchase.order.line'].browse(vals.get('purchase_line_id'))
            vals.update({'secondary_uom_id': purchase_line.secondary_uom_id.id,
                         'secondary_uom_qty': purchase_line.secondary_uom_qty})
        return super(StockMove, self).create(vals)

    @api.multi
    def split(self, qty, restrict_lot_id=False, restrict_partner_id=False):
        qty_previous = self.product_uom_qty
        new_move_id = super(StockMove, self).split(qty, restrict_lot_id=restrict_lot_id,
                                                   restrict_partner_id=restrict_partner_id)
        if not tools.float_is_zero(qty_previous, precision_digits=2):
            secondary_uom_qty = (1 - qty / qty_previous) * self.secondary_uom_qty
            self.write({'secondary_uom_qty': secondary_uom_qty
                        })
        return new_move_id

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        if default:
            if 'product_uom_qty' in default and 'secondary_uom_qty' not in default and 'secondary_uom_id' not in default and self.secondary_uom_id:
                qty_previous = self.product_uom_qty
                if not tools.float_is_zero(qty_previous, precision_digits=2):  # todo precision?
                    secondary_uom_qty = default.get('product_uom_qty') / qty_previous * self.secondary_uom_qty
                    default.update({'secondary_uom_qty': secondary_uom_qty})
        return super(StockMove, self).copy(default=default)

    @api.one
    def check_product_qty_constraint(self):
        quant_product_qty = sum(self.quant_ids.filtered(lambda r: r.qty > 0.0).mapped('qty'))
        product_qty = self.product_qty
        if not tools.float_is_zero(quant_product_qty - product_qty, precision_digits=5):
            raise exceptions.ValidationError(_('Nesutampa pervežtas kiekis. kreipkitės į sistemos administratorių'))
        if self.secondary_uom_id:
            product_uom_qty_theoretical = self.product_id.product_tmpl_id.convert_from_secondary_uom(
                self.secondary_uom_qty,
                self.secondary_uom_id,
                self.product_uom)
            if tools.float_compare(abs(self.product_uom_qty - product_uom_qty_theoretical),
                                   self.product_uom.rounding,
                                   precision_rounding=self.product_uom.rounding / 10) > 0:
                raise exceptions.ValidationError(
                    _('Nesutampa kiekiai skirtingais matavimo vienetais %s') % self.product_id.display_name)

    @api.multi
    def action_done(self):
        res = super(StockMove, self).action_done()
        self.check_product_qty_constraint()
        return res

    @api.onchange('product_id')
    def onch_prod_set_secondary_uom(self):
        if self.product_id and (not self.secondary_uom_id or self.secondary_uom_id not in self.product_id.product_uom_lines.mapped('uom_id')):
            self.secondary_uom_id = self.product_id.uom_id

    @api.multi
    def write(self, vals):
        if 'product_id' in vals and self.mapped('product_id.id') != [vals['product_id']] and (self.mapped('secondary_uom_id') or vals.get('secondary_uom_id')):
            trigger_secondary_uom_recompute = True
        else:
            trigger_secondary_uom_recompute = False
        res = super(StockMove, self).write(vals)
        if trigger_secondary_uom_recompute:
            self._set_product_qty_from_secondary()
        return res


StockMove()


class StockPackOperation(models.Model):
    _inherit = 'stock.pack.operation'

    secondary_uom_id = fields.Many2one('product.uom', string='Antrinis matavimo vienetas', compute='_secondary_uom')
    secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais', compute='_secondary_uom')

    @api.one
    def _secondary_uom(self):
        self.secondary_uom_id = self.product_uom_id
        qty_done = self.qty_done if not tools.float_is_zero(self.qty_done, precision_digits=5) else self.product_qty
        self.secondary_uom_qty = qty_done
        if not self.product_id:
            return
        stock_moves = self.picking_id.move_lines.filtered(lambda r: r.product_id == self.product_id)
        secondary_uom = stock_moves.mapped('secondary_uom_id')
        if len(secondary_uom) > 1:
            return
        if not secondary_uom:
            secondary_uom = self.product_uom_id
        try:
            secondary_uom_qty = self.product_id.product_tmpl_id.convert_to_secondary_uom(qty_done,
                                                                 self.product_uom_id,
                                                                 secondary_uom)
        except:
            return
        self.secondary_uom_qty = secondary_uom_qty
        self.secondary_uom_id = secondary_uom


StockPackOperation()
