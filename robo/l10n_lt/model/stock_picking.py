# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    invoice_ids = fields.One2many('account.invoice', 'picking_id', string='Sąskaitos', copy=False, sequence=100)
    origin_picking_ids = fields.Many2many('stock.picking', 'origin_stock_picking_for_returns_rel',
                                          'picking_id', 'origin_picking_id',
                                          string='Grąžinami važtaraščiai', sequence=100)
    origin_quant_ids = fields.Many2many('stock.quant', 'origin_stock_picking_stock_quant_rel', compute='_get_quant_ids',
                                        string='Grąžinami produktų kiekiai')
    quant_to_return_ids = fields.One2many('stock.quant.return', 'picking_id', string='Produktai grąžinimui',
                                          groups='stock.group_stock_manager', sequence=100)
    quant_ids = fields.Many2many('stock.quant', string='Produktai susiję su važtaraščiu',
                                 compute='_get_quant_ids')
    is_quant_selection_ok = fields.Boolean(compute='_is_quant_selection_ok', groups='stock.group_stock_manager',
                                           string='Važtaraštis atitinka pasirinktus produktus')
    is_picking_selection_enough = fields.Boolean(compute='_is_picking_selection_enough',
                                                 string='Pasirinkti važtaraščiai turi pakankamą kiekį',
                                                 groups='stock.group_stock_manager')
    is_out_refund = fields.Boolean(compute="_is_out_refund",
                                   string='Ar kreditinė sąskaita?')
    select_origin_picking = fields.Boolean(string='Pasirinkti grąžinamus važtaraščius rankiniu būdu', default=False,
                                           readonly=True, states={'draft': [('readonly', False)],
                                                                  'waiting': [('readonly', False)],
                                                                  'confirmed': [('readonly', False)]},
                                           sequence=100,
                                           )
    select_origin_quant = fields.Boolean(string='Pasirinkti grąžinamus produktų kiekius rankiniu būdu', default=False,
                                         readonly=True, states={'draft': [('readonly', False)],
                                                                'waiting': [('readonly', False)],
                                                                'confirmed': [('readonly', False)]},
                                         sequence=100,
                                         )
    show_add_return_quant_button = fields.Boolean(compute='_show_add_return_quant_button')

    @api.one
    @api.depends('origin_picking_ids', 'move_lines.quant_ids')
    def _get_quant_ids(self):
        if self.move_lines:
            self.quant_ids = [(6, 0, self.move_lines.mapped('quant_ids.id'))]
        if self.origin_picking_ids:
            quant_ids = self.origin_picking_ids.mapped('move_lines.quant_ids').filtered(
                lambda q: q.location_id.usage in ['customer', 'transit', 'view']
            )
            self.origin_quant_ids = [(6, 0, quant_ids.mapped('id'))]

    @api.one
    @api.depends('quant_to_return_ids.qty_to_return')
    def _is_quant_selection_ok(self):
        prod_qty = {}
        for move in self.move_lines:
            product_id = move.product_id.id
            qty = move.product_qty
            if product_id in prod_qty:
                prod_qty[product_id] += qty
            else:
                prod_qty[product_id] = qty
        res = True
        self.update_quant_availability()
        for product_id, qty in prod_qty.items():
            if float_compare(sum(self.quant_to_return_ids.filtered(
                    lambda p: p.quant_id.product_id.id == product_id).mapped('qty_to_return')),
                             qty, precision_digits=4) != 0:
                res = False
                break
        self.is_quant_selection_ok = res

    @api.one
    @api.depends('quant_to_return_ids.qty_to_return', 'origin_picking_ids')
    def _is_picking_selection_enough(self):
        """ Compute is_picking_selection_enough: indicates if the selected pickings have potentially enough products to
            move. It does not check for the quant availability """
        prod_qty = {}
        for move in self.move_lines:
            product_id = move.product_id.id
            qty = move.product_qty
            if product_id in prod_qty:
                prod_qty[product_id] += qty
            else:
                prod_qty[product_id] = qty
        res = True
        self.update_quant_availability()
        for product_id, qty in prod_qty.items():
            moves = self.origin_picking_ids.mapped('move_lines').filtered(
                lambda m:m.product_id.id == product_id
            )
            if float_compare(sum(moves.mapped('product_qty')), qty, precision_digits=4) < 0:
                res = False
                break
        self.is_picking_selection_enough = res

    @api.one
    @api.depends('error', 'location_id.usage', 'location_dest_id.usage')
    def _is_out_refund(self):
        if not self.error and self.location_id.usage == 'customer' and self.location_dest_id.usage == 'internal':
            self.is_out_refund = True

    @api.one
    @api.depends('origin_quant_ids', 'quant_to_return_ids')
    def _show_add_return_quant_button(self):
        if self.origin_quant_ids \
                and any([q.id not in self.quant_to_return_ids.mapped('quant_id.id') for q in self.origin_quant_ids]):
            self.show_add_return_quant_button = True

    @api.onchange('select_origin_quant', 'origin_quant_ids')
    def update_quants_to_return(self):
        res = [(5,)]
        res += [(0, 0, {'quant_id': p.id}) for p in self.origin_quant_ids
                if p not in self.quant_to_return_ids.mapped('quant_id')]

        res += [(0, 0, {'quant_id': p.quant_id.id, 'qty_to_return': p.qty_to_return})
                for p in self.quant_to_return_ids if p.quant_id in self.origin_quant_ids]

        res += [(2, q.id,) for q in self.quant_to_return_ids.filtered(
            lambda p: p.quant_id.id not in self.origin_quant_ids.mapped('id')
        )]
        self.quant_to_return_ids = res

    @api.multi
    def action_assign(self):
        unassigned = self.filtered(lambda p: not p.is_out_refund)
        refunds = self - unassigned
        for rec in refunds:
            if rec.select_origin_picking and not self.env.user.has_group('stock.group_stock_manager'):
                raise exceptions.UserError(
                    _('Negalite koreguoti šio važtaraščio. Kreipkitės į buhalterį.'))
            if rec.select_origin_picking and rec.select_origin_quant:
                if rec.is_quant_selection_ok:
                    return_use_quants = [(q.quant_id, q.qty_to_return) for q in rec.quant_to_return_ids
                                         if not tools.float_is_zero(q.qty_to_return, precision_digits=4)]
                    super(StockPicking, rec.with_context(return_use_quants=return_use_quants)).action_assign()
                    rec.update_quants_to_return()
                else:
                    raise exceptions.UserError(_('Nesutampa pasirinkti grąžinami kiekiai su bendru važtaraščio kiekiu.'))
            elif rec.select_origin_picking:
                if rec.is_picking_selection_enough and rec.origin_quant_ids:
                    super(StockPicking, rec.with_context(origin_quant_ids=rec.origin_quant_ids.ids)).action_assign()
                else:
                    raise exceptions.UserError(
                        _('Neužtenka pasirinktų grąžinamų važtaraščių kiekio.'))
            elif rec.origin_quant_ids.ids:
                super(StockPicking, rec.with_context(origin_quant_ids=rec.origin_quant_ids.ids)).action_assign()
            else:
                pickings = rec.invoice_ids._get_origin_picking_ids()
                quants = self.env['stock.picking'].browse(pickings).mapped('move_lines.non_error_quant_ids.id')
                if quants:
                    super(StockPicking, rec.with_context(origin_quant_ids=quants)).action_assign()
                if rec.state != 'assigned':
                    unassigned |= rec
        if unassigned:
            super(StockPicking, unassigned).action_assign()

    @api.multi
    def do_new_transfer(self):
        if self.select_origin_picking and not self.env.user.has_group('stock.group_stock_manager'):
            raise exceptions.UserError(
                _('Negalite koreguoti šio važtaraščio. Kreipkitės į buhalterį.'))
        return super(StockPicking, self).do_new_transfer()

    @api.multi
    def do_transfer(self):
        res = super(StockPicking, self).do_transfer()
        transfered_quants = self.mapped('move_lines.non_error_quant_ids')
        if self.select_origin_picking and self.select_origin_quant:
            for quant in self.quant_to_return_ids.filtered('qty_to_return'):
                if quant.quant_id not in transfered_quants or float_compare(
                        quant.qty_to_return,
                        sum(transfered_quants.filtered(lambda q: q.id == quant.quant_id.id).mapped('qty')),
                        precision_rounding=0.0001) != 0:
                    raise exceptions.UserError(_('Nepavyko perduoti kiekių.'))
        elif self.select_origin_picking:
            if transfered_quants and any([q not in self.origin_quant_ids for q in transfered_quants]):
                raise exceptions.UserError(_('Nepavyko perduoti pasirinktų kiekių.'))
        return res

    @api.one
    def update_quant_availability(self):
        self.quant_to_return_ids.update_quantities()
