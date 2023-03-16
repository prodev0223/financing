# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, exceptions, fields, _, tools
from odoo.tools import float_compare
from datetime import datetime

ALLOWED_ERROR = 0.01  # Might allow an error of 0.02 if necessary


class MRPunbuid(models.Model):
    _inherit = 'mrp.unbuild'
    _mail_post_access = 'read'

    def get_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    build_date = fields.Datetime(string='Data', default=get_date, required=True)
    state = fields.Selection([('draft', 'Juodraštis'), ('reserved', 'Rezervuota'), ('done', 'Išrinkta')])
    price_ids = fields.One2many('mrp.unbuild.prices', 'unbuild_id', string='Komponentų savikainos', readonly=True,
                                states={'reserved': [('readonly', False)]})
    consume_value = fields.Float(string='Bendra vertė', compute='_consume_value')

    @api.multi
    def recompute_proportion(self):
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        qty = sum(rec.qty for rec in self.price_ids) if self.price_ids else 0.0
        if not tools.float_is_zero(qty, precision_digits=precision):
            self._consume_value()
            # P3:DivOK
            unit_price = tools.float_round(
                self.consume_value / qty, precision_digits=3)
            self.price_ids.write({'price_unit': unit_price})
            self.normalize_recursively()

    def normalize_recursively(self):
        lowest_qty = self.price_ids.sorted(key=lambda r: r.qty)[0]
        direction = changed_direction = False
        current_total = tools.float_round(sum(rec.total_value for rec in self.price_ids), precision_digits=2)
        iter_count = 0
        while tools.float_compare(abs(self.consume_value - current_total), ALLOWED_ERROR, precision_digits=2) > 0:
            iter_count += 1
            if tools.float_compare(self.consume_value, current_total, precision_digits=2) < 0:
                lowest_qty.price_unit -= 0.001
                new_direction = 'down'
            if tools.float_compare(self.consume_value, current_total, precision_digits=2) > 0:
                lowest_qty.price_unit += 0.001
                new_direction = 'up'
            current_total = tools.float_round(sum(rec.total_value for rec in self.price_ids), precision_digits=2)
            if not direction:
                direction = new_direction
            elif new_direction != direction:
                if changed_direction:
                    break
                changed_direction = True
                direction = new_direction
            if iter_count >= 100:
                break

    @api.one
    @api.depends('consume_line_ids.quant_ids', 'consume_line_ids.reserved_quant_ids')
    def _consume_value(self):
        self.consume_value = sum(self.consume_line_ids.mapped('quant_ids').mapped(lambda r: r.cost*r.qty))\
                             + sum(self.consume_line_ids.mapped('reserved_quant_ids').mapped(lambda r: r.cost*r.qty))

    @api.onchange('product_id')
    def onchange_product_id(self):
        """
        Complete override of the addons method
        using build date as a priority date in
        the context, instead of create date
        :return: None
        """
        if self.product_id:
            date = self.build_date or self.create_date
            self.bom_id = self.env['mrp.bom'].with_context(bom_at_date=date)._bom_find(product=self.product_id)
            self.product_uom_id = self.product_id.uom_id.id

    @api.multi
    def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None, force=True):

        # ROBO allow post to the accountant:
        # model_name = self._name
        # if model_name:
        #     DocModel = self.env[model_name]
        # else:
        #     DocModel = self
        # if hasattr(DocModel, '_mail_post_access'):
        #     create_allow = True
        # else:
        #     create_allow = False

        res = super(MRPunbuid, self).message_subscribe(partner_ids=partner_ids, channel_ids=channel_ids,
                                                       subtype_ids=subtype_ids, force=force, create_allow=True)
        return res

    @api.multi
    def reserve(self):
        self.ensure_one()
        consume_move = self.consume_line_ids
        if not consume_move:
            consume_move = self._generate_consume_moves()[0]
        # force location update
        consume_move.write({
            'location_id': self.location_id.id,
            'date_expected': self.build_date
        })
        # Search quants that passed production order
        qty = self.product_qty  # Convert to qty on product UoM
        if self.mo_id:
            finished_moves = self.mo_id.move_finished_ids.filtered(
                lambda move: move.product_id == self.mo_id.product_id)
            domain = [('qty', '>', 0), ('history_ids', 'in', finished_moves.ids)]
        else:
            domain = [('qty', '>', 0)]
        quants = self.env['stock.quant'].quants_get_preferred_domain(
            qty, consume_move,
            domain=domain,
            preferred_domain_list=[],
            lot_id=self.lot_id.id)
        self.env['stock.quant'].quants_reserve(quants, consume_move)
        if consume_move.state == 'assigned':
            self.state = 'reserved'
            if not self.produce_line_ids:
                if self.product_id.tracking != 'none' and not self.lot_id.id:
                    raise exceptions.UserError(_('Nurodykite SN numerius'))
                self._generate_produce_moves()
            self.create_prices()
            self.recompute_proportion()
        else:
            raise exceptions.Warning(_('Rezervavimas nepavyko, nepakankamas produktų kiekis!'))

    @api.multi
    def create_prices(self):
        UnbuildPrice = self.env['mrp.unbuild.prices']
        for rec in self:
            produce_moves = rec.produce_line_ids
            if rec.price_ids:
                rec.price_ids.unlink()
            for produce_move in produce_moves:
                UnbuildPrice.create({
                    'unbuild_id': rec.id,
                    'product_id': produce_move.product_id.id,
                    'price_unit': produce_move.price_unit_forced,
                    'qty': produce_move.product_uom_qty,
                })

    @api.multi
    def unreserve(self):
        self.ensure_one()
        consume_move = self.consume_line_ids
        if consume_move:
            consume_move.do_unreserve()
            if consume_move.state == 'assigned':
                raise exceptions.UserError(_('Nepavyko atšaukti rezervacijos'))
        self.produce_line_ids.unlink()
        self.state = 'draft'

    @api.multi
    def action_unbuild(self):
        self.ensure_one()
        if self.product_id.tracking != 'none' and not self.lot_id.id:
            raise exceptions.UserError(_('Nurodykite SN numerius'))

        consume_move = self.env['stock.move'].search([('consume_unbuild_id', '=', self.id)])[0]
        if not consume_move:
            raise exceptions.UserError(_('Rezervuokite komponentus.'))
        produce_moves = self.produce_line_ids
        if not produce_moves:
            raise exceptions.UserError(_('Nesukurti gaminių perkėlimai.'))
        if not self.price_ids:
            raise exceptions.UserError(_('Nesudėtos gaminių savikainos.'))

        # Search quants that passed production order
        qty = self.product_qty  # Convert to qty on product UoM
        if self.mo_id:
            finished_moves = self.mo_id.move_finished_ids.filtered(
                lambda move: move.product_id == self.mo_id.product_id)
            domain = [('qty', '>', 0), ('history_ids', 'in', finished_moves.ids)]
        else:
            domain = [('qty', '>', 0)]
        quants = self.env['stock.quant'].quants_get_preferred_domain(
            qty, consume_move,
            domain=domain,
            preferred_domain_list=[],
            lot_id=self.lot_id.id)
        self.env['stock.quant'].quants_reserve(quants, consume_move)

        if consume_move.has_tracking != 'none':
            self.env['stock.move.lots'].create({
                'move_id': consume_move.id,
                'lot_id': self.lot_id.id,
                'quantity_done': consume_move.product_uom_qty,
                'quantity': consume_move.product_uom_qty})
        else:
            consume_move.quantity_done = consume_move.product_uom_qty
        consume_move.move_validate()
        original_quants = consume_move.quant_ids.mapped('consumed_quant_ids')

        for produce_move in produce_moves:
            if produce_move.has_tracking != 'none':
                raise exceptions.UserError(_('Negalima išardyti į komponentus, kurie sekami SN.'))
                original = original_quants.filtered(lambda quant: quant.product_id == produce_move.product_id)
                self.env['stock.move.lots'].create({
                    'move_id': produce_move.id,
                    'lot_id': original.lot_id.id,
                    'quantity_done': produce_move.product_uom_qty,
                    'quantity': produce_move.product_uom_qty
                })
            else:
                produce_move.quantity_done = produce_move.product_uom_qty
        for price_id in self.price_ids:
            produce_moves.filtered(lambda r: r.product_id.id == price_id.product_id.id).write({
                'price_unit': price_id.price_unit,
            })
        produce_moves.move_validate()
        produced_quant_ids = produce_moves.mapped('quant_ids').filtered(lambda quant: quant.qty > 0)
        consume_move.quant_ids.sudo().write({'produced_quant_ids': [(6, 0, produced_quant_ids.ids)]})
        # sanity check
        value1 = sum(consume_move.mapped('quant_ids').mapped(lambda r: r.qty*r.cost))
        value2 = sum(produce_moves.mapped('quant_ids').mapped(lambda r: r.qty*r.cost))
        if float_compare(abs(value1 - value2), ALLOWED_ERROR, precision_digits=2) > 0:
            raise exceptions.UserError(_('Nesutampa vertės. Bendra išardytų produktų vertė turi būti %s, o ne %s')
                                       % (value1, value2))
        self.write({'state': 'done'})

    # @api.multi
    # def action_unbuild(self):
    #     self.ensure_one()
    #     if self.mo_id and float_compare(self.product_qty, self.mo_id.product_qty, precision_digits=2) != 0:  # todo uom
    #         raise exceptions.Warning(_('Galima išardyti tik pilną gamybos užsakymą'))
    #     if self.mo_id and self.env['mrp.unbuild'].search_count([('mo_id', '=', self.mo_id.id), ('state', '=', 'done')]):
    #         raise exceptions.Warning(_('Tas pats gamybos užsakymas gali būti išardytas tik vieną kartą '))
    #         # no accounting entries will be created, since revaluation will be done
    #     res = super(MRPunbuid, self.with_context(no_moves=True, look_in_noninternal_locations=True)).action_unbuild()
    #     quant_ids = self.consume_line_ids.mapped('quant_ids')
    #     control_value = sum([r.qty * r.cost for r in quant_ids])
    #     values = {}
    #     qtys = {}
    #     prices = {}
    #     production_qtys = {}
    #     production_qty = 0
    #     control_value2 = 0.0
    #     for quant in quant_ids:
    #         if quant.qty < 0:
    #             continue
    #         production_qty += quant.qty
    #         production_id = quant.mapped('history_ids.production_id')
    #         if len(production_id) > 1:
    #             raise exceptions.Warning(_('Too many manufacturing orders detected.'))
    #         if not production_id:
    #             tot_qty = 0.0
    #             for move in self.sudo().produce_line_ids:
    #                 if move.product_id.type == 'product':
    #                     tot_qty += move.product_uom_qty
    #             unit_price = control_value / tot_qty
    #             for move in self.sudo().produce_line_ids:
    #                 if move.product_id.type == 'product':
    #                     move.price_unit = unit_price
    #             control_value2 = sum(
    #                 [r.qty * r.cost for r in self.sudo().produce_line_ids.mapped('quant_ids')])
    #             if float_compare(control_value, control_value2, precision_digits=2) != 0:
    #                 raise exceptions.UserError(_('Internal error. Values do not match.'))
    #         if production_id.id not in production_qtys:
    #             production_qtys[production_id.id] = quant.qty
    #         else:
    #             production_qtys[production_id.id] += quant.qty
    #         for move in production_id.mapped('move_raw_ids'):
    #             value = sum([r.qty * r.cost if r.qty > 0.0 else 0.0 for r in move.quant_ids])
    #             qty = move.product_uom_qty
    #             if move.product_id.id not in values:
    #                 values[move.product_id.id] = value
    #                 qtys[move.product_id.id] = qty
    #             else:
    #                 values[move.product_id.id] += value
    #                 qtys[move.product_id.id] += qty
    #         for k in values.keys():
    #             if k not in prices:
    #                 prices[k] = values[k] / qtys[k] * quant.qty
    #             else:
    #                 prices[k] += values[k] / qtys[k] * quant.qty
    #         values = {}
    #         qtys = {}
    #         for k in prices.keys():
    #             prices[k] = prices[k] / production_qty
    #         # delete link between dismantled products and lots
    #         quant_ids.write({'lot_id': False})
    #         for move in self.sudo().produce_line_ids:
    #             if move.product_id.id in prices and (move.product_id.type == 'product' or (
    #                     move.product_id.type != 'product')):
    #                 cost = prices[move.product_id.id]
    #                 move.price_unit = cost
    #                 value = move.price_unit * move.product_uom_qty
    #                 control_value2 += value
    #                 prices.pop(move.product_id.id)
    #         if float_compare(control_value, control_value2, precision_digits=2):
    #             raise exceptions.UserError(_('Values do not match. Contact system administrator'))
    #         # create accounting entries
    #         for move in self.sudo().produce_line_ids:
    #             for quant in move.quant_ids:
    #                 quant._account_entry_move(move)
    #     return res

    @api.multi
    def open_account_move_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree,form,pivot',
            'view_type': 'form',
            'views': [(False, 'tree'), (False, 'form'), (False, 'pivot')],
            'target': 'self',
            'context': {'search_default_name': self.name}
        }
