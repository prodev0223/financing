# -*- coding: utf-8 -*-
from __future__ import division
import logging
from odoo import models, fields, api, _, exceptions, tools
from odoo.addons import decimal_precision as dp
from datetime import datetime


_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _is_reverse(self):
        if self._context.get('reverse', False):
            return True
        else:
            return False

    is_reverse = fields.Boolean(string='Grąžinimas', default=_is_reverse)
    show_accounting = fields.Boolean(compute='_show_accounting')
    move_count = fields.Integer(compute='_move_count')
    show_reverse = fields.Boolean(compute='_show_reverse')
    error = fields.Boolean(string='Klaidų taisymas', default=False, sequence=100)
    allow_force_assign = fields.Boolean(compute='_allow_force_assign')
    shipping_type = fields.Selection(
        [('transfer', 'Pervežimas'), ('return', 'Grąžinimas')],
        string='Važtaraščio tipas', required=True, default='transfer',
        states={'done': [('readonly', True)],
                'cancel': [('readonly', True)]})
    original_picking_id = fields.Many2one('stock.picking', compute='_compute_original_picking_id', store=True,
                                          sequence=100,
                                          )
    cancel_childs = fields.One2many('stock.picking', 'original_picking_id', sequence=100)
    has_cancels = fields.Boolean(string='Turi atšaukimų', compute='_compute_has_cancels', store=True)
    date = fields.Datetime(copy=False)

    @api.multi
    def action_confirm(self):
        res = super(StockPicking, self).action_confirm()
        self.action_assign()
        return res

    @api.one
    @api.depends('move_lines', 'error')
    def _compute_original_picking_id(self):
        if not self.error:
            self.original_picking_id = False
            return

        origin_return_move_ids = self.move_lines.mapped('origin_returned_move_id')
        ultimate_parent = False
        dead_counter = 100

        while len(origin_return_move_ids) > 0 and dead_counter > 0:
            parent_pickings = origin_return_move_ids.mapped('picking_id')
            #  should have the same parent_picking!
            if len(parent_pickings) > 0:
                ultimate_parent = parent_pickings[0]
                origin_return_move_ids = ultimate_parent.move_lines.mapped('origin_returned_move_id')
            dead_counter -= 1

        if ultimate_parent and dead_counter > 0:
            self.original_picking_id = ultimate_parent

    @api.one
    @api.depends('cancel_childs.state', 'original_picking_id')
    def _compute_has_cancels(self):
        self.has_cancels = False
        if not self.original_picking_id and self.state == 'done':
            if len(self.cancel_childs.filtered(lambda r: r.state == 'done')) > 0:
                self.has_cancels = True
            else:
                self.has_cancels = False

    @api.onchange('shipping_type')
    def onchange_shipping_type(self):
        if self.shipping_type != 'transfer':
            self.location_id = self.env.ref('stock.stock_location_customers').id
        else:
            self.location_id = self.picking_type_id.default_location_src_id.id if (
                    self.picking_type_id and self.picking_type_id.default_location_src_id) else False

    @api.one
    @api.depends('location_dest_id.usage')
    def _allow_force_assign(self):
        if self.location_id.usage == 'internal':
            self.allow_force_assign = False
        else:
            self.allow_force_assign = True

    @api.model
    def _prepare_values_extra_move(self, op, product, remaining_qty):
        res = super(StockPicking, self)._prepare_values_extra_move(op, product, remaining_qty)
        if res['group_id'] and not res['procurement_id']:
            group = self.env['procurement.group'].browse(res['group_id'])
            if 'SO' in group.name and group.procurement_ids.filtered(lambda r: r.product_id.id == product.id):
                res['procurement_id'] = group.procurement_ids.filtered(lambda r: r.product_id.id == product.id)[0].id
        return res

    #FIXME: _show_reverse and _show_accounting are very similar. Could be made one call only
    @api.one
    @api.depends('location_id.usage', 'location_dest_id.usage')
    def _show_reverse(self):
        if self.location_dest_id.usage == 'customer' and self.location_id.usage == 'internal' \
                or self.location_dest_id.usage == 'internal' and self.location_id.usage in ['supplier', 'transit']:
            self.show_reverse = True
        else:
            self.show_reverse = False

    @api.one
    def _move_count(self):
        self.move_count = len(self.move_lines)

    @api.one
    @api.depends('location_id.usage', 'location_dest_id.usage')
    def _show_accounting(self):
        if (self.location_id.usage == 'internal' and self.location_dest_id.usage != 'internal') or (
                self.location_id.usage != 'internal' and self.location_dest_id.usage == 'internal'):
            self.show_accounting = True
        else:
            self.show_accounting = False

    @api.multi
    def _create_backorder(self, backorder_moves=[]):
        res = super(StockPicking, self)._create_backorder(backorder_moves)
        for rec in res:
            rec.error = rec.backorder_id.error
        return res

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
            'context': {'search_default_ref': self.name}
        }

    @api.multi
    def unlink(self):
        self.mapped('pack_operation_ids').unlink()
        for picking in self:
            _logger.info('User %s tried deleting picking %s (Related document: %s)', self.env.user.id, picking.name, picking.origin)
        return super(StockPicking, self).unlink()


StockPicking()


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    cost = fields.Float(digits=(16, 16))
    supplier_id = fields.Many2one('res.partner', string='Tiekėjas', compute='_supplier_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Klientas', compute='_client_id', store=True)
    non_error_history_ids = fields.Many2many(
        'stock.move', 'non_error_stock_quant_move_rel', 'quant_id', 'move_id',
        string='Neatšaukti judėjimai', copy=False,
        help='Tikri judėjimai')

    @api.one
    @api.depends('history_ids')
    def _supplier_id(self):
        for move in self.history_ids:
            if move.picking_id.location_dest_id.usage == 'internal' and \
                    move.picking_id.location_id.usage == 'supplier' and move.picking_partner_id:
                self.supplier_id = move.picking_partner_id
                break

    @api.one
    @api.depends('history_ids')
    def _client_id(self):
        for move in self.history_ids:
            if (move.picking_id.location_id.usage == 'internal' and
                move.picking_id.location_dest_id.usage == 'customer') or \
                    (move.picking_id.location_id.usage == 'customer' and
                     move.picking_id.location_dest_id.usage == 'internal') and move.picking_partner_id:
                self.partner_id = move.picking_partner_id
                break

    @api.multi
    def _quant_split(self, qty):
        """
        !COMPLETE OVERRIDE OF ADD-ONS _quant_split method!
        """
        self.ensure_one()
        rounding = self.product_id.uom_id.rounding
        if tools.float_compare(abs(self.qty), abs(qty), precision_rounding=rounding) <= 0:
            return False
        qty_round = tools.float_round(qty, precision_rounding=rounding)
        new_qty_round = tools.float_round(self.qty - qty, precision_rounding=rounding)
        # Fetch the history_ids manually as it will not do a join with the stock moves then (=> a lot faster)
        self._cr.execute("""SELECT move_id FROM stock_quant_move_rel WHERE quant_id = %s""", (self.id,))
        res = self._cr.fetchall()
        new_quant = self.sudo().copy(
            default={'qty': new_qty_round, 'history_ids': [(4, x[0]) for x in res]})
        self._cr.execute("""SELECT move_id FROM non_error_stock_quant_move_rel WHERE quant_id = %s""", (self.id,))
        res = self._cr.fetchall()

        new_quant.with_context(recompute=False).write({
            'non_error_history_ids': [(4, x[0]) for x in res],
        })
        self.env.cache.clear()

        self.sudo().write({'qty': qty_round})
        return new_quant

    @api.multi
    @api.constrains('qty')
    def negative_check(self):
        """
        Ensure that quant is non negative or zero
        if product is not consumable
        :return:
        """
        for rec in self.filtered(lambda x: x.product_id.type != 'consu'):
            # Get the rounding from related product, and choose the most minimal
            # rounding. In case of False uom_id 'or' condition is added
            min_rounding = 0.000001
            rounding = min(rec.product_id.uom_id.rounding or min_rounding, min_rounding)
            if tools.float_compare(rec.qty, 0, precision_rounding=rounding) <= 0:
                msg = str()
                if rec.lot_id:
                    msg = '\nSN: %s' % rec.lot_id.name
                raise exceptions.ValidationError(
                    _('Produkto kiekis negali būti neigiamas ar lygus 0! Produkto %s kiekis %s.%s') % (
                        rec.product_id.name, rec.qty, msg)
                )

    @api.model
    def create(self, vals):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        qty = vals.get('qty')
        if tools.float_compare(qty, 0.0, precision_digits=precision) < 0:
            product = self.env['product.product'].browse(vals.get('product_id')).exists()
            if product.type != 'consu':
                raise exceptions.ValidationError(
                    _('Produkto kiekis negali būti neigiamas! Produkto %s kiekis %s.') % (product.name, qty)
                )

        res = super(StockQuant, self).create(vals)
        allow_zero_value = self.env.user.company_id.sudo().allow_zero_value_quant
        cmp_cost = tools.float_compare(res.cost, 0, precision_digits=8)
        if (cmp_cost == 0 and not allow_zero_value or cmp_cost < 0) and not self._context.get('no_raise'):
            if res.lot_id:
                msg = '\nSN: %s' % res.lot_id.name
            else:
                msg = ''
            raise exceptions.ValidationError(
                _('Produkto vieneto savikaina negali būti neigiama ar lygi 0! Produkto %s savikaina %s.%s') %
                (res.product_id.name, res.cost, msg))
        return res

    @api.multi
    @api.constrains('lot_id')
    def constrain_lot_unique(self):
        for rec in self.filtered('lot_id'):
            rec.lot_id.constrain_quant_unique()


StockQuant()


class StockMove(models.Model):
    _inherit = 'stock.move'

    current_value = fields.Float(string='Current Value', compute='_current_value', inverse='_set_value')
    inventory_line_id = fields.Many2one('stock.inventory.line', string='Inventorizacijos eilutė', readonly=True)
    invoice_line_id = fields.Many2one('account.invoice.line', string='Sąskaitos faktūros eilutė')
    non_error_quant_ids = fields.Many2many('stock.quant', 'non_error_stock_quant_move_rel', 'move_id', 'quant_id',
                                           string='Perkelti kiekiai', copy=False)
    product_uom_qty = fields.Float(lt_string='Originalus kiekis')
    non_error_qty = fields.Float(string='Kiekis', compute='_compute_non_error_qty', store=True,
                                 digits=dp.get_precision('Product Unit of Measure'))

    @api.multi
    @api.constrains('product_uom_qty')
    def _check_product_uom_qty(self):
        """Ensure that product QTY is not less than zero"""
        for rec in self:
            quantity = rec.product_uom_qty
            if tools.float_compare(0.0, quantity, precision_rounding=rec.product_id.uom_id.rounding) >= 0:
                raise exceptions.ValidationError(
                    _('Produkto kiekis negali būti neigiamas arba lygus nuliui! Produkto %s kiekis %s.') % (
                        rec.product_id.name, quantity)
                )

    @api.multi
    @api.depends('state', 'error', 'product_uom_qty')
    def _compute_non_error_qty(self):
        """Check whether original move quantity matches quantity from quants and raise if it does not"""
        check_qty = self.env.context.get('check_quantities')
        for rec in self:
            # non error quantity is always the same
            # as quantity if state is not in done or cancel
            if rec.state not in ['done', 'cancel']:
                rec.non_error_qty = rec.product_uom_qty
                continue
            non_error_qty = sum(rec.non_error_quant_ids.mapped('qty'))
            # Check difference if product is not consumable and move is not draft
            if check_qty and rec.product_id.type != 'consu' and rec.state == 'done':
                diff = tools.float_round(abs(rec.product_uom_qty - non_error_qty), precision_digits=0)
                if diff > 1:
                    error_diff = tools.float_round(
                        abs(rec.product_uom_qty - sum(rec.quant_ids.mapped('qty'))), precision_digits=0)
                    # If there's a difference, check the difference between all (including error) quant IDs
                    if error_diff > 1:
                        raise exceptions.ValidationError(_('Neatitikimas tarp sandėlio judėjimo kiekių'))
            rounding = rec.product_id.uom_id.rounding or 0.001
            # Only write the value if there's difference - Impacts multi threading a lot
            if tools.float_compare(rec.non_error_qty, non_error_qty, precision_rounding=rounding):
                rec.non_error_qty = non_error_qty

    @api.one
    def calculate_non_error_quants(self):
        if self.error and self.origin_returned_move_id:
            self.non_error_quant_ids = [(5,)]
            return
        error_moves = self.env['stock.move']
        additional_err_moves = self.env['stock.move'].search([('error', '=', True),
                                                              ('origin_returned_move_id', 'in', self.ids)])
        while additional_err_moves:
            error_moves |= additional_err_moves
            additional_err_moves = self.env['stock.move'].search([('error', '=', True),
                                                                  ('origin_returned_move_id', 'in', additional_err_moves.ids)])
        error_moves.write({'non_error_quant_ids': [(5,)]})
        if error_moves and self.quant_ids:
            back_moves = error_moves.filtered(lambda m: m.location_dest_id.id == self.location_id.id)
            # TODO: should we explicitely filter for location_id.id == self.location_id.id ?
            forth_moves = error_moves - back_moves
            if back_moves:
                self._cr.execute('''
                SELECT quant_id, count FROM 
                    (SELECT quant_id, count(*) count 
                    FROM stock_quant_move_rel
                    WHERE quant_id in %s
                        AND move_id in %s
                    GROUP by quant_id) foo
                ''', (tuple(self.quant_ids.ids), tuple(back_moves.ids)))
                back_quants = {q: c for q, c in self._cr.fetchall()}
            else:
                back_quants = dict()
            if forth_moves:
                self._cr.execute('''
                SELECT quant_id, count FROM 
                    (SELECT quant_id, count(*) count 
                    FROM stock_quant_move_rel
                    WHERE quant_id in %s
                        AND move_id in %s
                    GROUP by quant_id) foo
                ''', (tuple(self.quant_ids.ids),
                      tuple(error_moves.filtered(lambda m: m.location_id.id == self.location_id.id).ids)))
                forth_quants = {q: c for q, c in self._cr.fetchall()}
            else:
                forth_quants = dict()
            error_quant_ids = []
            for qid in self.quant_ids.ids:
                back = back_quants.get(qid, 0)
                forth = forth_quants.get(qid, 0)
                if back - forth == 1:
                    error_quant_ids += [qid]
                elif back - forth != 0:
                    raise exceptions.UserError(
                        _('Šis judėjimas negali būti atšauktas. Jei manote, kad tai klaida, susisiekite su buhalteriu.'))
        else:
            error_quant_ids = []
        nonerror_quants = self.quant_ids - self.env['stock.quant'].browse(error_quant_ids)
        nonerror_quant_ids = nonerror_quants.ids
        self.non_error_quant_ids = [(6, 0, nonerror_quant_ids)]


    @api.multi
    def _current_value(self):
        for rec in self:
            rec.current_value = sum(q.qty * q.cost for q in rec.quant_ids)

    @api.multi
    def _set_value(self):
        for rec in self:
            total_value = rec.current_value
            total_qty = sum(q.qty for q in rec.quant_ids)
            for quant in rec.quant_ids:
                quant.cost = total_value / total_qty  # P3:DivOK

    def default_error(self):
        if self._context.get('error', False):
            return True
        else:
            return False

    error = fields.Boolean(string='Klaidų taisymas', compute='_error', store=True)
    error_move = fields.Boolean(string='Priverstinis klaidų taisymas', default=default_error, copy=False)
    is_reverse = fields.Boolean(string='Grąžinimas', related='picking_id.is_reverse', store=True, lt_string='Grąžinimas')

    @api.depends('picking_id.error', 'error_move')
    @api.one
    def _error(self):
        if self.sudo().picking_id and self.sudo().picking_id.error:
            self.error = True
        elif self.error_move:
            self.error = True
        else:
            self.error = False

    @api.multi
    def action_done(self):
        pickings = self.mapped('picking_id')
        if len(pickings) > 1:
            raise exceptions.UserError(_('Vienu metu galima patvirtinti tik vieną važtaraštį'))
        try:
            if pickings:
                force_date = pickings[0].min_date
                super(StockMove, self.with_context(force_period_date=force_date)).action_done()
                for rec in self:
                    rec.date = force_date
                    if rec.location_id.usage != 'internal' and rec.location_dest_id.usage == 'internal' \
                            and not rec.origin_returned_move_id and (
                            rec.picking_id and rec.picking_id.shipping_type == 'transfer'):
                        rec.quant_ids.sudo().write({'in_date': force_date})
            else:
                super(StockMove, self).action_done()
        except (exceptions.UserError, exceptions.ValidationError) as exc:
            raise exc
        except Exception as exc:
            import traceback
            _logger.info('Picking confirm failed | ids: %s | error: %s \nTraceback: %s' %
                         (str(pickings.ids), tools.ustr(exc), traceback.format_exc()))
            body = _('Nepavyko patvirtinti sandėlio judėjimų.')
            if self.env.user.has_group('robo_basic.group_robo_premium_accountant'):
                body += '\n Sisteminis pranešimas: {}'.format(exc.args[0] if exc.args else str())
            raise exceptions.ValidationError(body)

        for move in self:
            if move.error and move.origin_returned_move_id and move.product_id.type != 'consu':
                if not set(move.quant_ids.ids).issubset(move.origin_returned_move_id.quant_ids.ids):
                    raise exceptions.UserError(_('Nepavyko pervežti tų pačių prekių (produktas %s)') % move.product_id.display_name)
        for move in self:
            parent = move
            while parent.error and parent.origin_returned_move_id:
                parent = parent.origin_returned_move_id
            parent.calculate_non_error_quants()

    @api.multi
    def _get_accounting_data_for_valuation(self):
        if self.error and self.origin_returned_move_id:
            parent_move = self.origin_returned_move_id
            while parent_move.error and parent_move.origin_returned_move_id:
                parent_move = parent_move.origin_returned_move_id
            journal_id, acc_src, acc_dest, acc_valuation = parent_move._get_accounting_data_for_valuation()
            location_from = self.location_id
            location_to = self.location_dest_id
            if parent_move.location_id != self.location_id and\
                    location_from.usage not in ['supplier', 'customer'] and\
                    location_to.usage not in ['supplier', 'customer']:
                acc_src, acc_dest = acc_dest, acc_src
            return journal_id, acc_src, acc_dest, acc_valuation
        accounts = self.product_id.product_tmpl_id.get_product_accounts()
        if self.location_id.valuation_out_account_id:
            acc_src = self.location_id.valuation_out_account_id.id
        else:
            acc_src = accounts['stock_input'].id
        if self.location_dest_id.valuation_in_account_id:
            acc_dest = self.location_dest_id.valuation_in_account_id.id
        else:
            acc_dest = accounts['stock_output'].id

        acc_valuation = accounts.get('stock_valuation', False)
        if acc_valuation:
            acc_valuation = acc_valuation.id

        if self.raw_material_production_id:
            product_id = self.raw_material_production_id.product_id
            categ_id = product_id.categ_id
            while not categ_id.property_stock_valuation_account_id and categ_id.parent_id:
                categ_id = categ_id.parent_id
            if categ_id.property_stock_valuation_account_id:
                acc_dest = categ_id.property_stock_valuation_account_id.id
            else:
                raise exceptions.UserError(
                    _('Atsargų apskaitos sąskaita nenurodyta gaminamam produktui %s') % product_id.name)
        elif self.unbuild_id:
            categ_id = self.unbuild_id.product_id.categ_id
            while not categ_id.property_stock_valuation_account_id and categ_id.parent_id:
                categ_id = categ_id.parent_id
            valuation_account_id = categ_id.property_stock_valuation_account_id
            if valuation_account_id and self.product_id.type != 'consu':
                acc_src = valuation_account_id.id
            elif valuation_account_id and self.product_id.type == 'consu':
                acc_src = acc_valuation
                acc_valuation = valuation_account_id.id
            else:
                raise exceptions.UserError(
                    _('Nenustatyta atsargų apskaitos sąskaita produktui %s') % self.unbuild_id.product_id.name)
        journal_id = accounts['stock_journal'].id
        parent_move = self
        while parent_move.origin_returned_move_id and parent_move.picking_id.shipping_type != 'return':
            parent_move = parent_move.origin_returned_move_id
        if parent_move.picking_id.shipping_type == 'return':
            product_cost_account = self.product_id.product_cost_account_id or self.product_id.categ_id.product_cost_account_id
            if not product_cost_account:
                categ_id = self.product_id.categ_id
                while not categ_id.product_cost_account_id and categ_id.parent_id:
                    categ_id = categ_id.parent_id
                if categ_id.product_cost_account_id:
                    product_cost_account = categ_id.product_cost_account_id
            if product_cost_account:
                acc_src = acc_dest = product_cost_account.id
            else:
                raise exceptions.Warning(_('Produkto %s grąžinimo saskaita nesukonfigūruota') % self.product_id.name)
        if self.scrapped:
            product = self.product_id
            if product.account_scrap:
                acc_dest = product.account_scrap.id
            elif product.product_tmpl_id.account_scrap:
                acc_dest = product.product_tmpl_id.account_scrap.id
            elif product.categ_id.account_scrap:
                acc_dest = product.categ_id.account_scrap.id
        # if self.inventory_line_id and not self.inventory_line_id.account_id:
        #     raise exceptions.Warning(_('Nenurodyta inventorizacijos nurašymo sąskaita'))

        # Temporary fix for front-end behaviour. When front-end has account selection implemented, remove fix
        # and uncomment the two previous lines
        if self.inventory_line_id and not self.inventory_line_id.account_id:
            if self.inventory_id and self.inventory_id.account_id:
                self.inventory_line_id.account_id = self.inventory_id.account_id
            elif not self.inventory_id.representation_inventory:
                raise exceptions.Warning(_('Nenurodyta inventorizacijos nurašymo sąskaita'))
        # End of temporary fix

        if self.inventory_line_id and self.inventory_line_id.account_id and not self.origin_returned_move_id:
            acc_dest = self.inventory_line_id.account_id.id
        elif self.inventory_line_id and self.inventory_line_id.account_id and self.origin_returned_move_id:
            acc_src = self.inventory_line_id.account_id.id

        if not journal_id:
            raise exceptions.UserError(_('Nenurodytas operacijų žurnalas. Kreipkitės į buhalterį.'))

        if not acc_src and self.location_dest_id.usage == 'inventory':
            raise exceptions.UserError(_('Neteisingi %s produkto nustatymai. Kreipkitės į buhalterį.')
                                       % self.product_id.name)
        if not acc_dest and self.location_dest_id.usage != 'inventory':
            raise exceptions.UserError(_('Neteisingi %s produkto nustatymai. Kreipkitės į buhalterį.')
                                       % self.product_id.name)
        if not acc_valuation:
            raise exceptions.UserError(
                _('Neteisingi nustatymai (produktas - %s, kategorija - %s). Kreipkitės į buhalterį.')
                % (self.product_id.name, self.product_id.categ_id.name))

        return journal_id, acc_src, acc_dest, acc_valuation

    @api.multi
    def get_price_unit(self):
        """ Returns the unit price to store on the quant """
        self.ensure_one()
        date = self.picking_id.date and self.picking_id.date[:10] or self.date and self.date[:10]
        self = self.with_context(date=date)
        if self.sudo().purchase_line_id:
            price_unit = self.sudo().purchase_line_id._get_stock_move_price_unit()
            self.write({'price_unit': price_unit})
            return price_unit
        res = super(StockMove, self).get_price_unit()
        invoice = self.sudo().invoice_line_id.invoice_id
        if invoice:
            if not res and invoice.type == 'out_refund':
                res = self.product_id.avg_cost
                if not res:
                    product_lines = invoice.invoice_line_ids.filtered(lambda r: r.product_id == self.product_id)
                    cost = sum(product_lines.mapped('price_subtotal'))
                    qty = sum(product_lines.mapped('quantity'))
                    if qty > 0:
                        res = cost / qty  # P3:DivOK
            if invoice.type == 'in_invoice':
                # Always take newest price from invoice in case invoice was modified in extended stock mode
                res = self.sudo().invoice_line_id.price_subtotal_signed / self.product_uom_qty \
                    if self.product_uom_qty != 0 else 0.0  # P3:DivOK

        return res

    @api.multi
    def action_assign(self, no_prepare=False):
        error_moves = self.filtered(lambda m: m.error and m.origin_returned_move_id and m.product_id.type != 'consu')
        non_error_moves = self - error_moves
        error_moves.action_error_assign()
        super(StockMove, non_error_moves).action_assign(no_prepare=no_prepare)

    @api.multi
    def action_error_assign(self):
        for move in self:
            if move.state == 'assigned' and move.reserved_quant_ids and not self.env.context.get('no_state_change'):
                continue
            if move.error and move.origin_returned_move_id:
                quant_ids = move.origin_returned_move_id.mapped('quant_ids')
                if len(quant_ids.mapped('product_id.id')) > 1:
                    raise exceptions.UserError(_('Klaida atšaukiant'))
                reservations = quant_ids.mapped('reservation_id')
                if reservations:
                    msg = _('Negalima atšaukti, prekės rezervuotos.')
                    if self.env.user.is_accountant():
                        move_names = ', '.join(res.picking_id.name
                                               if res.picking_id else (res.name or str()) for res in reservations)
                        msg += _('\nProduct: %s (%s)') % ((move.product_id.default_code
                                                           or move.product_id.name), move_names)
                        if self.env.user._is_admin():
                            msg += _('; Moves: %s') % str(reservations.ids)
                    raise exceptions.UserError(msg)
                # if self._context.get('simplified_stock', False):
                location_ids = quant_ids.mapped('location_id.id')
                if move.product_id.type == 'product':
                    if len(location_ids) != 1:
                        raise exceptions.UserError(_('Klaida atšaukiant'))
                    if location_ids != [move.location_id.id]:
                        raise exceptions.UserError(_('Klaida atšaukiant'))
                    if tools.float_compare(sum(quant_ids.mapped('qty')), move.product_qty,
                                           precision_digits=self.env['decimal.precision'].precision_get(
                                               'Product Unit of Measure')) != 0:
                        if self.env.user._is_admin():
                            msg = _('Negalima atšaukti move_id: %s, product: %s, %s != %s') % (
                                move.id, move.product_id.display_name, sum(quant_ids.mapped('qty')), move.product_qty)
                        else:
                            msg = _('Negalima atšaukti.')
                        raise exceptions.UserError(msg)
        # we checked if everything just in case we raise
        for move in self:
            if move.state == 'assigned' and move.reserved_quant_ids and not self.env.context.get('no_state_change'):
                continue
            quant_ids = move.origin_returned_move_id.mapped('quant_ids').filtered(lambda r: r.location_id.id == move.location_id.id)
            qty = move.product_qty
            for q in quant_ids.sudo().filtered(lambda r: not r.reservation_id):
                if qty > 0.0 and tools.float_compare(q.qty, qty, precision_digits=2) <= 0:
                    q.reservation_id = move.id
                    qty -= q.qty
            if not tools.float_is_zero(qty, precision_digits=self.env['decimal.precision'].precision_get(
                                       'Product Unit of Measure')):
                raise exceptions.UserError(_('Nepavyko rezervuoti prekių.'))
            move.write({'state': 'assigned'})
        if self.mapped('picking_id'):
            self.check_recompute_pack_op()
        return True

    # @api.multi
    # def action_error_assign(self):
    #     # returns True if succesful else returns False
    #     for move in self:
    #         if move.error and move.origin_returned_move_id:
    #             quant_ids = move.origin_returned_move_id.mapped('quant_ids')
    #             location_ids = quant_ids.mapped('location_id.id')
    #             if len(quant_ids.mapped('product_id.id')) > 1:
    #                 return False
    #             if len(location_ids) != 1:
    #                 return False
    #             if location_ids != [move.location_id.id]:
    #                 return False
    #             if quant_ids.mapped('reservation_id'):
    #                 return False
    #             if tools.float_compare(sum(quant_ids.mapped('qty')), move.product_qty,
    #                                    precision_digits=self.env['decimal.precision'].precision_get(
    #                                        'Product Unit of Measure')) != 0:
    #                 if self.env.user._is_admin():
    #                     msg = _('Wrong configuration move_id: %s, product: %s, %s != %s') % (
    #                     move.id, move.product_id.display_name, sum(quant_ids.mapped('qty')), move.product_qty)
    #                 else:
    #                     msg = _('Wrong configuration.')
    #                 raise exceptions.UserError(msg)
    #         else:
    #             return False
    #     # we checked if everything just in case we raise
    #     for move in self:
    #         quant_ids = move.origin_returned_move_id.mapped('quant_ids')
    #         location_ids = quant_ids.mapped('location_id.id')
    #         if len(quant_ids.mapped('product_id.id')) > 1:
    #             raise exceptions.UserError(_('You can only return 1 product.'))
    #         if len(location_ids) != 1:
    #             raise exceptions.UserError(
    #                 _('Product was moved to other location and cannot be reversed.'))
    #         if location_ids != [move.location_id.id]:
    #             raise exceptions.UserError(
    #                 _('Product was moved to other location and cannot be reversed.'))
    #         if quant_ids.mapped('reservation_id'):
    #             raise exceptions.UserError(
    #                 _('Dismantled product is already reserved for another stock move and cannot be dismantled.'))
    #         if tools.float_compare(sum(quant_ids.mapped('qty')), move.product_qty,
    #                                precision_digits=self.env['decimal.precision'].precision_get(
    #                                    'Product Unit of Measure')) != 0:
    #             raise exceptions.UserError(_('Wrong configuration.'))
    #         qty = move.product_qty
    #         for q in quant_ids.sudo().filtered(lambda r: not r.reservation_id):
    #             if qty > 0.0 and q.qty <= qty:
    #                 q.reservation_id = move.id
    #                 qty -= q.qty
    #         # quant_ids.sudo().write({'reservation_id': rec.move_lines.id})
    #         move.write({'state': 'assigned'})
    #     return True


StockMove()


class StockLocation(models.Model):
    _inherit = 'stock.location'

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', compute='_warehouse_id', store=True)
    display_name_stored = fields.Char(compute='_compute_display_name_stored', store=True)

    # Stored compute can't depend on non-stored display_name, thus other vals are used
    @api.multi
    @api.depends('complete_name', 'name')
    def _compute_display_name_stored(self):
        """
        Computes stored display name that is
        identical to display_name (System field unchanged)
        """
        for rec in self:
            rec.display_name_stored = rec.display_name

    @api.multi
    @api.constrains('location_id')
    def location_id_constraint(self):
        for rec in self:
            if rec.location_id and rec.location_id.usage != 'view':
                raise exceptions.ValidationError(_('Tėvinė lokacija privalo būti rodinys.'))

    @api.one
    @api.depends('usage', 'location_id.usage', 'name', 'location_id.name', 'location_id.warehouse_id')
    def _warehouse_id(self):
        if self.usage != 'view':
            parent = self
            while parent and parent.usage != 'view':
                parent = parent.location_id
            if parent:
                warehouse = self.sudo().env['stock.warehouse'].search([('view_location_id', '=', parent.id)], limit=1)
                if warehouse:
                    self.warehouse_id = warehouse.id
                    return
        else:
            warehouse = self.sudo().env['stock.warehouse'].search([('view_location_id', '=', self.id)], limit=1)
            if warehouse:
                self.warehouse_id = warehouse.id
                return

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.search(['|', ('complete_name', operator, name),
                            ('display_name_stored', operator, name)] + args, limit=limit)
        return recs.name_get()


StockLocation()


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model
    def create(self, vals):
        res = super(StockWarehouse, self).create(vals)
        res.view_location_id._warehouse_id()  # somehow computes are not triggered during create
        res.lot_stock_id._warehouse_id()
        res.wh_input_stock_loc_id._warehouse_id()
        res.wh_qc_stock_loc_id._warehouse_id()
        res.wh_output_stock_loc_id._warehouse_id()
        res.wh_pack_stock_loc_id._warehouse_id()
        return res


StockWarehouse()


class StockInventoryLine(models.Model):
    _inherit = 'stock.inventory.line'

    consumed_qty = fields.Float(string='Change in Quantity (+ or -)',
                                digits=dp.get_precision('Product Unit of Measure'), copy=True)
    product_qty = fields.Float(compute='_product_qty', inverse='_set_product_qty')
    date = fields.Datetime(string='Date', related='inventory_id.date', store=True)
    account_id = fields.Many2one('account.account', string='Force Stock Account', copy=False)
    changed = fields.Boolean(string='Changed', default=False)
    currency_id = fields.Many2one('res.currency', string='Currency', related='inventory_id.currency_id')
    move_ids = fields.One2many('stock.move', 'inventory_line_id', copy=False)
    total_value = fields.Monetary(string='Cost', currency_field='currency_id', store=True,
                                  compute='_compute_total_value')

    @api.onchange('consumed_qty')
    def onchange_consumed_qty(self):
        if self.consumed_qty and self.consumed_qty > 0 and not self.changed:
            self.consumed_qty = -self.consumed_qty
            self.changed = True

    @api.model
    def create(self, vals):
        inventory_id = vals.get('inventory_id', False)
        return super(StockInventoryLine, self.with_context(creating_with_inventory_id=inventory_id)).create(vals)

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self._context.get('creating_with_inventory_id', False):
            args += [('inventory_id', '!=', self._context.get('creating_with_inventory_id', False))]
        return super(StockInventoryLine, self).search(args, offset=0, limit=limit, order=order, count=count)

    @api.one
    @api.depends('theoretical_qty', 'consumed_qty')
    def _product_qty(self):
        th_qty = self.theoretical_qty or 0.0
        c_qty = self.consumed_qty or 0.0
        self.product_qty = th_qty + c_qty

    @api.one
    def _set_product_qty(self):
        if self.product_qty > 0.0:
            self.consumed_qty = self.product_qty - self.theoretical_qty

    @api.depends('move_ids.state')
    def _compute_total_value(self):
        for rec in self:
            precision_rounding = rec.currency_id.rounding
            total_value = 0
            for move in rec.sudo().move_ids.filtered(lambda r: r.state == 'done'):
                if move.location_dest_id.usage != 'internal':
                    sign = 1
                else:
                    sign = -1
                total_value += tools.float_round(sign * move.current_value, precision_rounding=precision_rounding)
            rec.total_value = total_value

    @api.multi
    def _generate_moves(self):
        moves = self.env['stock.move']
        Quant = self.env['stock.quant']
        for line in self:
            if tools.float_compare(line.theoretical_qty, line.product_qty,
                                   precision_rounding=line.product_id.uom_id.rounding) == 0:
                continue
            diff = line.theoretical_qty - line.product_qty
            vals = {
                'name': _('INV:') + (line.inventory_id.name or ''),
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'date': line.inventory_id.date,
                'company_id': line.inventory_id.company_id.id,
                'inventory_id': line.inventory_id.id,
                'inventory_line_id': line.id,
                'state': 'confirmed',
                'restrict_lot_id': line.prod_lot_id.id,
                'restrict_partner_id': line.partner_id.id
            }
            if diff < 0:  # found more than expected
                vals['location_id'] = line.product_id.property_stock_inventory.id
                vals['location_dest_id'] = line.location_id.id
                vals['product_uom_qty'] = abs(diff)
            else:
                vals['location_id'] = line.location_id.id
                vals['location_dest_id'] = line.product_id.property_stock_inventory.id
                vals['product_uom_qty'] = diff
            move = moves.create(vals)

            if diff > 0:
                domain = [('qty', '>', 0.0),
                          ('package_id', '=', line.package_id.id),
                          ('lot_id', '=', line.prod_lot_id.id),
                          ('location_id', '=', line.location_id.id)]
                preferred_domain_list = [[('reservation_id', '=', False)],
                                         [('reservation_id.inventory_id', '!=', line.inventory_id.id)]]
                quants = Quant.quants_get_preferred_domain(
                    move.product_qty, move, domain=domain, preferred_domain_list=preferred_domain_list
                )
                Quant.quants_reserve(quants, move)
            elif line.package_id:
                move.action_done()
                move.quant_ids.write({'package_id': line.package_id.id})
                quants = Quant.search([('qty', '<', 0.0),
                                       ('product_id', '=', move.product_id.id),
                                       ('location_id', '=', move.location_dest_id.id),
                                       ('package_id', '!=', False)], limit=1)
                if quants:
                    for quant in move.quant_ids:
                        if quant.location_id.id == move.location_dest_id.id:  # To avoid already reconciled quants
                            quant._quant_reconcile_negative(move)
        return moves


StockInventoryLine()


class StockInventory(models.Model):
    _name = 'stock.inventory'
    _inherit = ['stock.inventory', 'mail.thread']

    _order = 'date desc'

    def _default_accounting_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    company_id = fields.Many2one('res.company', string='Company', store=True, readonly=True,
                                 related='location_id.company_id')
    accounting_date = fields.Date(string='Apskaitos data', help='', default=_default_accounting_date,
                                  states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    total_value = fields.Monetary(string='Nurašymų vertė', compute='_total_value', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Valiuta', compute='_currency_id')
    number = fields.Char(string='Numeris', readonly=True, copy=False)
    account_id = fields.Many2one('account.account', string='Nurašymo sąskaita',
                                 required=False, readonly=False, lt_string='Nurašymo sąskaita',
                                 default=lambda self: self.env['account.account'].search([('code', '=', '6318')], limit=1).id,
                                 states={'done': [('readonly', True)]})
    date = fields.Datetime(string='Koregavimo data')
    location_id = fields.Many2one(string='Atsargų vieta')
    filter = fields.Selection(string='Koregavimas')
    reason_details = fields.Char(string='Detailed reason')

    @api.one
    def _currency_id(self):
        self.currency_id = self.env.user.sudo().company_id.currency_id.id

    @api.one
    @api.depends('move_ids.state')
    def _total_value(self):
        total_value = 0
        precision_rounding = self.currency_id.rounding
        for move in self.sudo().move_ids.filtered(lambda r: r.state == 'done'):
            if move.location_dest_id.usage != 'internal':
                sign = 1
            else:
                sign = -1
            total_value += tools.float_round(sign * move.current_value, precision_rounding=precision_rounding)
        self.total_value = total_value

    def _get_inventory_lines_values(self):
        res = super(StockInventory, self)._get_inventory_lines_values()
        if self.account_id:
            for line in res:
                line['account_id'] = self.account_id.id
        return res

    @api.multi
    def action_cancel_draft_inventory(self):
        """ Cancels draft records """
        self.filtered(lambda i: i.state == 'draft').write({'state': 'cancel'})

    @api.multi
    def cancel_state_done(self):
        self.ensure_one()
        if self.state != 'done':
            raise exceptions.Warning(_('Inventory has not been validated'))
        for line in self.line_ids:
            stock_moves = self.env['stock.move'].search([('inventory_line_id', '=', line.id)])
            for stock_move in stock_moves.sudo():
                reverse_move = stock_move.copy({'location_dest_id': stock_move.location_id.id,
                                                'location_id': stock_move.location_dest_id.id,
                                                'error_move': True,
                                                'origin_returned_move_id': stock_move.id,
                                                })
                reverse_move.action_assign()
                if self.accounting_date:
                    reverse_move.with_context(force_period_date=self.accounting_date).action_done()
                else:
                    reverse_move.with_context(no_date_force=True).action_done()
        self.state = 'cancel'

    @api.one
    def reset_real_qty(self):
        for line in self.line_ids:
            line.product_qty = 0
            line.consumed_qty = -line.theoretical_qty

    @api.multi
    def action_done(self):
        for rec in self:
            rec.number = self.env['ir.sequence'].next_by_code('stock_inventory')
            super(StockInventory, self.with_context(default_ref=rec.number)).action_done()
        for rec in self:
            if not rec.accounting_date:
                raise exceptions.Warning(_('Privaloma įvesti apskaitos datą, kad galėtumėte vykdyti koregavimą.'))
            rec.move_ids.sudo().write({'date': rec.accounting_date, 'date_expected': rec.accounting_date})
        return

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise exceptions.UserError(_('Negalima ištrinti patvirtinto atsargų nurašymo. '
                                             'Pabandykite atšaukti atsargų nurašymą.'))
        return super(StockInventory, self).unlink()

    @api.multi
    def recalculate_theoretical_qty(self):
        """Manually recompute theoretical qty for each line.
        Too much things impact this field, cannot depend on all of them"""
        self.line_ids._compute_theoretical_qty()


StockInventory()


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def default_error(self):
        if self._context.get('error', False):
            return True
        else:
            return False

    error = fields.Boolean(string='Fixing Mistake', default=default_error, copy=False)
    mistake_type = fields.Selection([('cancel', 'Atšaukti'), ('modify', 'Keisti')], default='cancel', help="")
    deny_picking_return = fields.Boolean(compute='_deny_picking_return')
    deny_return_message = fields.Text(compute='_deny_picking_return')

    @api.one
    def _deny_picking_return(self):
        picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
        deny_picking_return = False
        deny_return_message = _('Negalima atlikti grąžinimo\n')
        if picking:
            if picking.state != 'done':
                deny_picking_return = True
                deny_return_message += _('Galite atlikti grąžinimą tik tiems važtaraščiams kurie yra išsiųsti!\n')
            for stock_move in picking.move_lines:
                if stock_move.scrapped:
                    continue
                original_qty = sum(stock_move.mapped('quant_ids.qty'))
                returnable_quantity = sum(quant.qty for quant in self.env['stock.quant'].search([
                    ('history_ids', 'in', stock_move.id),
                    ('qty', '>', 0.0), ('location_id', 'child_of', stock_move.location_dest_id.id)
                ]).filtered(
                    lambda q: not q.reservation_id or q.reservation_id.origin_returned_move_id != stock_move)
                )  # It's actually much faster to search and filter in this case (tested with the timer, saves 2 sec)
                # Plus, search does not behave correctly if origin_returned_move_id is empty

                if tools.float_compare(original_qty, returnable_quantity, precision_digits=3) != 0:
                    deny_picking_return = True
                    deny_return_message += _('Dalis produkto {} kiekio buvo parduotas. \n').format(
                        stock_move.product_id.display_name)
        else:
            deny_picking_return = True
            deny_return_message += _('Nerastas susijęs važtaraštis\n')
        self.deny_return_message = deny_return_message
        self.deny_picking_return = deny_picking_return

    @api.multi
    def _create_returns(self):
        self.product_return_moves.write({'to_refund_so': True})
        error_modify = self.error and self.mistake_type == 'modify'
        if error_modify:
            res = self.create_copy_picking()
        if self.error:
            picking_id = self._context.get('active_id', False)
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.sudo().sale_id.state == 'done':
                raise exceptions.UserError(
                    _('Negalima taisyti važtaraščių, kai pardavimas jau užrakintas. Pirmiau atrakinkite pardavimą.'))
            new_picking_id, pick_type_id = super(StockReturnPicking, self.with_context(error=self.error))._create_returns()
            self.sudo().env['account.invoice'].search([('picking_id', '=', picking_id)]).write({'picking_id': False})
        else:
            new_picking_id, pick_type_id = super(StockReturnPicking, self.with_context(reverse=True))._create_returns()
        new_picking = self.env['stock.picking'].browse(new_picking_id)
        if self.error:
            new_picking.error = True
            active_id = self._context.get('active_id', False)
            if active_id:
                old_picking = self.env['stock.picking'].browse(active_id)
                new_picking.origin = old_picking.origin
        else:
            new_picking.is_reverse = True
        if new_picking.location_dest_id.usage == 'internal' and not self.error:
            new_picking.shipping_type = 'return'
        if self.error:
            new_picking.action_assign()
            for operation_line in new_picking.pack_operation_product_ids:
                for pack_lot in operation_line.pack_lot_ids:
                    if pack_lot.lot_id:
                        pack_lot.action_add_quantity(1)
            new_picking.do_transfer()
            qty_to_cancel_by_product = {}
            for l in self.product_return_moves:
                product_id = l.product_id.id
                qty = l.move_id.product_uom._compute_quantity(l.quantity, l.product_id.uom_id, round=False)
                if product_id not in qty_to_cancel_by_product:
                    qty_to_cancel_by_product[product_id] = qty
                else:
                    qty_to_cancel_by_product[product_id] += qty
            qty_cancelled_by_product = {}
            for l in new_picking.move_lines.filtered(lambda r: r.state == 'done'):
                product_id = l.product_id.id
                qty = l.product_qty
                if product_id not in qty_cancelled_by_product:
                    qty_cancelled_by_product[product_id] = qty
                else:
                    qty_cancelled_by_product[product_id] += qty
            product_ids = set(qty_to_cancel_by_product.keys() + qty_cancelled_by_product.keys())
            for product_id in product_ids:
                qty_to_cancel = qty_to_cancel_by_product.get(product_id, 0.0)
                qty_cancelled = qty_cancelled_by_product.get(product_id, 0.0)
                if tools.float_compare(qty_to_cancel, qty_cancelled, precision_digits=5) != 0:
                    raise exceptions.UserError(_('Nepavyko atšaukti. Grįžkite į važtaraštį ir atšaukite per naują'))

        if error_modify:
            return res
        return new_picking_id, pick_type_id

    @api.multi
    def create_copy_picking(self):
        picking_id = self._context.get('active_id', False)
        pick_obj = self.env['stock.picking']
        data_obj = self.env['stock.return.picking.line']
        pick = pick_obj.browse(picking_id)
        data = self.read()[0]
        returned_lines = 0

        # Create new picking for returned products
        new_picking = pick.with_context(error=False).copy({
            'move_lines': [],
            'state': 'draft',
            'origin': pick.origin,
        })

        for data_get in data_obj.browse(data['product_return_moves']):
            move = data_get.move_id
            if not move:
                raise exceptions.UserError(_("Ištrinkite ranka pridėtas eilutes"))
            new_qty = data_get.quantity
            if new_qty:
                returned_lines += 1
                new_move = move.with_context(error=False).copy({
                    'picking_id': new_picking.id,
                    'state': 'draft',
                })
                new_move.purchase_line_id = move.purchase_line_id.id  # it is not copied by default
        if not returned_lines:
            raise exceptions.UserError(_("Nurodykite bent vieną nenulinį kiekį"))
        return new_picking.id, new_picking.picking_type_id.id


StockReturnPicking()


class StockReturnPickingLine(models.TransientModel):
    _inherit = "stock.return.picking.line"

    to_refund_so = fields.Boolean(string='Grąžinti', help='', default=True)


StockReturnPickingLine()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    comment = fields.Html(string='Comment', readonly=True,
                          states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, copy=False,
                          sequence=100,
                          )
    picking_ids = fields.Many2many('stock.picking', compute='_compute_picking_ids',
                                   string='Picking associated to this sale')

    @api.multi
    @api.depends('procurement_group_id', 'name')
    def _compute_picking_ids(self):
        for order in self:
            if order.procurement_group_id:
                domain = ['|', ('origin', '=like', order.name), ('group_id', '=', order.procurement_group_id.id)]
            else:
                domain = [('origin', '=like', order.name)]
            order.picking_ids = self.env['stock.picking'].search(domain)
            order.delivery_count = len(order.picking_ids)


SaleOrder()


class StockScrap(models.Model):
    _inherit = 'stock.scrap'
    #FIXME: Should we implent that ? it's overloading the default method
    @api.multi
    def do_scrap(self):  # todo
        raise exceptions.UserError(_('Negalima atlikti šios operacijos. Susisiekite su sistemos administratoriumi'))


StockScrap()


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    account_scrap = fields.Many2one('account.account', string='Broko sąnaudų sąskaita', sequence=100)
    acc_product_type = fields.Selection([('product', 'Produktas'),
                                         ('service', 'Paslauga')],
                                        string='Produkto apskaitos tipas', required=True,
                                        default='product', track_visibility='onchange')
    weight = fields.Float(copy=True)
    default_code = fields.Char(copy=True)
    volume = fields.Float(copy=True)
    name = fields.Char(inverse='_set_name')
    categ_id = fields.Many2one(inverse='_set_categ_id')
    # System product that is not shown to the user
    robo_product = fields.Boolean(string='Sisteminis produktas', sequence=100)
    supplier_id = fields.Many2one('res.partner', string='Supplier')

    @api.multi
    def _set_name(self):
        """
        Inverse //
        If product name is the same as it's category name, mark it as system product
        :return: None
        """
        for rec in self:
            if rec.categ_id.name == rec.name:
                rec.robo_product = True

    @api.multi
    def _set_categ_id(self):
        """
        Set the same product accounting type as in product category
        :return: None
        """
        for rec in self:
            rec.acc_product_type = rec.categ_id.acc_product_type

    @api.multi
    @api.constrains('type')
    def _check_type(self):
        """Check if consumable product type can be set"""
        allow_consumables = self.sudo().env.user.company_id.allow_consumable_products
        for rec in self:
            if rec.type == 'consu' and not allow_consumables:
                raise exceptions.ValidationError(
                    _('Produkto tipas "Suvartojamas produktas" naudojamas labai '
                      'retais atvejais - rekomenduojame pasitikrinti ar tikrai norėjote pasirinkti '
                      'šį tipą vietoje sandėliuojamo ir tokiu atveju susisiekti su administratoriais dėl įgalinimo.')
                )

    @api.multi
    @api.constrains('type', 'categ_id')
    def check_matching_product_type_and_cost_method(self):
        for rec in self:
            if rec.type in ['consu', 'product'] and rec.categ_id.property_cost_method != 'real' or\
                    rec.type == 'service' and rec.categ_id.property_cost_method == 'real':
                raise exceptions.ValidationError(
                    _('Produkto tipas nesuderinamas su kategorija.'))

    @api.multi
    @api.constrains('type')
    def type_constrains(self):
        for rec in self:
            if rec.sudo().env['stock.quant'].search_count(
                    [('product_id.product_tmpl_id', '=', rec.id)]) and rec.type == 'service':
                raise exceptions.ValidationError(
                    _('Negalima keisti %s produkto tipo, egzistuoja sandėlio judėjimų.') % rec.name)

    @api.constrains('invoice_policy')
    def _check_invoice_policy(self):
        for rec in self:
            if rec.type == 'service' and rec.invoice_policy == 'delivery':
                raise exceptions.ValidationError(_('Paslaugos tipo produkto sąskaitų faktūrų išrašymo politika '
                                                   'negali būti "Pristatytais kiekiais".'))

    @api.model
    def set_accounting_product_type(self):
        product_templates = self.with_context(active_test=False).search([])
        for prod_tmpl in product_templates:
            if prod_tmpl.type != 'product':
                acc_prod_type = 'service'
            else:
                acc_prod_type = 'product'
            prod_tmpl.write({'acc_product_type': acc_prod_type})

    # @api.one
    # @api.constrains('acc_product_type', 'type')
    # def constr_acc_prod_type(self):
    #     if self.type == 'service' and self.acc_product_type != 'service':
    #         raise exceptions.ValidationError(_('Paslaugos apskaitos tipas privalo būti paslauga'))


    @api.onchange('type')
    def onch_set_acc_product_type(self):
        if self.type != 'product':
            acc_prod_type = 'service'
        else:
            acc_prod_type = 'product'
        self.acc_product_type = acc_prod_type
        self.onchange_acc_product_type()

    @api.onchange('acc_product_type', 'landed_cost_ok')
    def onchange_acc_product_type(self):
        if self.landed_cost_ok:
            # If landed cost ok is checked, change default category to cost_adjustments
            self.categ_id = self.env['product.category'].search(
                [('accounting_category_type', '=', 'cost_adjustments')], limit=1).id
        elif self.acc_product_type == 'product' or self.type == 'consu':
            self.categ_id = self.env.ref('l10n_lt.product_category_1').id
        else:
            self.categ_id = self.env.ref('l10n_lt.product_category_2').id

    @api.model
    def create(self, vals):
        if vals.get('type', False) and not vals.get('acc_product_type', False):
            vals['acc_product_type'] = vals['type']
        # default_code is lost when creating product variants
        if vals.get('default_code'):
            return super(ProductTemplate, self.with_context(default_default_code=vals['default_code'])).create(vals)
        else:
            return super(ProductTemplate, self).create(vals)

    @api.multi
    def unlink(self):
        if any(x.robo_product for x in self):
            raise exceptions.UserError(_('Negalite ištrinti sisteminių produktų'))
        return super(ProductTemplate, self).unlink()

    @api.multi
    def load_supplier(self):
        self.ensure_one()
        product = self.env['product.product'].search([('product_tmpl_id', '=', self.id)], limit=1)
        # Get the last one
        supplier = self.env['stock.quant'].search([('product_id', '=', product.id),
                                                   ('supplier_id', '!=', False)],
                                                  order='in_date desc', limit=1).mapped('supplier_id')
        if supplier:
            self.write({
                'supplier_id': supplier.id
            })


ProductTemplate()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.onchange('type')
    def onch_set_acc_product_type(self):
        if self.type != 'product':
            acc_prod_type = 'service'
        else:
            acc_prod_type = 'product'
        self.acc_product_type = acc_prod_type

    @api.onchange('acc_product_type')
    def onchange_acc_product_type(self):
        if self.acc_product_type == 'product':
            self.categ_id = self.env.ref('l10n_lt.product_category_1').id
        else:
            self.categ_id = self.env.ref('l10n_lt.product_category_2').id

    @api.model
    def create(self, vals):
        # default_code is lost when creating product variants
        if vals.get('default_code'):
            return super(ProductProduct, self.with_context(default_default_code=vals['default_code'])).create(vals)
        else:
            return super(ProductProduct, self).create(vals)

    @api.multi
    def get_product_income_account(self, return_default=False):
        """
        Returns the income account of the product.
        Loop through all of the categories if it's not set
        :param return_default: Indicates whether default, 5001 account
        should be returned if no product account was found
        :return: account.account record
        """
        self.ensure_zero_or_one()
        product_account = self.property_account_income_id
        if not product_account:
            category = self.categ_id
            while category.parent_id and not category.property_account_income_categ_id:
                category = category.parent_id
            product_account = category.property_account_income_categ_id
        if not product_account and return_default:
            product_account = self.env['account.account'].search(
                [('code', '=', '5001')], limit=1)
        return product_account

    @api.multi
    def get_product_expense_account(self, return_default=False):
        """
        Returns the expense account of the product.
        Loop through all of the categories if it's not set
        :param return_default: Indicates whether default, 6001 account
        should be returned if no product account was found
        :return: account.account record
        """
        self.ensure_one()
        product_account = self.property_account_expense_id
        if not product_account:
            category = self.categ_id
            while category.parent_id and not category.property_account_expense_categ_id:
                category = category.parent_id
            product_account = category.property_account_expense_categ_id
        if not product_account and return_default:
            product_account = self.env['account.account'].search(
                [('code', '=', '6001')], limit=1)
        return product_account


class ResPartner(models.Model):
    _inherit = 'res.partner'

    service_level = fields.Float()
    property_stock_customer = fields.Many2one(track_visibility='onchange')
    property_stock_supplier = fields.Many2one(track_visibility='onchange')


ResPartner()


class ReportStockForecast(models.Model):
    _inherit = 'report.stock.forecast'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Partneris')
    location_id = fields.Many2one('stock.location', string='Vieta')
    warehouse_id = fields.Many2one('stock.warehouse', string='Sandėlis')
    cumulative_quantity = fields.Float(string='Sukauptas kiekis')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'report_stock_forecast')
        self._cr.execute("""CREATE or REPLACE VIEW report_stock_forecast AS (SELECT
  MIN(FINAL.id)          AS id,
  FINAL.product_id       AS product_id,
  FINAL.date             AS date,
  sum(FINAL.product_qty) AS quantity,
  sum(sum(product_qty))
  OVER (PARTITION BY product_id, FINAL.partner_id, FINAL.location_id
    ORDER BY date) AS cumulative_quantity,
  FINAL.partner_id       AS partner_id,
  FINAL.location_id      AS location_id,
  stock_location.warehouse_id    AS warehouse_id
FROM
  (SELECT
     MIN(id)          AS id,
     MAIN.product_id  AS product_id,
     SUB.date         AS date,
     MAIN.partner_id  AS partner_id,
     MAIN.location_id AS location_id,
     CASE WHEN MAIN.date = SUB.date
       THEN sum(MAIN.product_qty)
     ELSE 0 END       AS product_qty
   FROM
     (SELECT
        MIN(sq.id)                                                 AS id,
        sq.product_id,
        to_date(to_char(CURRENT_DATE, 'YYYY/MM/DD'), 'YYYY/MM/DD') AS date,
        SUM(sq.qty)                                                AS product_qty,
        sq.partner_id                                              AS partner_id,
        sq.location_id                                             AS location_id
      FROM
        stock_quant AS sq
        LEFT JOIN
        product_product ON product_product.id = sq.product_id
        LEFT JOIN
        stock_location location_id ON sq.location_id = location_id.id
      WHERE
        location_id.usage = 'internal'
      GROUP BY date, sq.product_id, sq.partner_id, sq.location_id
      UNION ALL
      SELECT
        MIN(-sm.id)              AS id,
        sm.product_id,
        CASE WHEN sm.date_expected > CURRENT_DATE
          THEN to_date(to_char(sm.date_expected, 'YYYY/MM/DD'), 'YYYY/MM/DD')
        ELSE to_date(to_char(CURRENT_DATE, 'YYYY/MM/DD'), 'YYYY/MM/DD') END
                                 AS date,
        SUM(sm.product_qty)      AS product_qty,
        (CASE WHEN sm.picking_partner_id IS NOT NULL
          THEN sm.picking_partner_id
         ELSE sm.partner_id END) AS partner_id,
        sm.location_dest_id      AS location_id
      FROM
        stock_move AS sm
        LEFT JOIN
        product_product ON product_product.id = sm.product_id
        LEFT JOIN
        stock_location dest_location ON sm.location_dest_id = dest_location.id
        LEFT JOIN
        stock_location source_location ON sm.location_id = source_location.id
      WHERE
        sm.state IN ('confirmed', 'assigned', 'waiting') AND
        source_location.usage != 'internal' AND dest_location.usage = 'internal'
      GROUP BY sm.date_expected, sm.product_id, sm.picking_partner_id, sm.partner_id, sm.location_dest_id
      UNION ALL
      SELECT
        MIN(-sm.id)              AS id,
        sm.product_id,
        CASE WHEN sm.date_expected > CURRENT_DATE
          THEN to_date(to_char(sm.date_expected, 'YYYY/MM/DD'), 'YYYY/MM/DD')
        ELSE to_date(to_char(CURRENT_DATE, 'YYYY/MM/DD'), 'YYYY/MM/DD') END
                                 AS date,
        SUM(-(sm.product_qty))   AS product_qty,
        (CASE WHEN sm.picking_partner_id IS NOT NULL
          THEN sm.picking_partner_id
         ELSE sm.partner_id END) AS partner_id,
        sm.location_id           AS location_id
      FROM
        stock_move AS sm
        LEFT JOIN
        product_product ON product_product.id = sm.product_id
        LEFT JOIN
        stock_location source_location ON sm.location_id = source_location.id
        LEFT JOIN
        stock_location dest_location ON sm.location_dest_id = dest_location.id
      WHERE
        sm.state IN ('confirmed', 'assigned', 'waiting') AND
        source_location.usage = 'internal' AND dest_location.usage != 'internal'
      GROUP BY sm.date_expected, sm.product_id, sm.picking_partner_id, sm.partner_id, sm.location_id
      UNION ALL
      SELECT
        MIN(-sm.id)              AS id,
        sm.product_id,
        CASE WHEN sm.date_expected > CURRENT_DATE
          THEN to_date(to_char(sm.date_expected, 'YYYY/MM/DD'), 'YYYY/MM/DD')
        ELSE to_date(to_char(CURRENT_DATE, 'YYYY/MM/DD'), 'YYYY/MM/DD') END
                                 AS date,
        SUM(-(sm.product_qty))   AS product_qty,
        (CASE WHEN sm.picking_partner_id IS NOT NULL
          THEN sm.picking_partner_id
         ELSE sm.partner_id END) AS partner_id,
        sm.location_id           AS location_id
      FROM
        stock_move AS sm
        LEFT JOIN
        product_product ON product_product.id = sm.product_id
        LEFT JOIN
        stock_location source_location ON sm.location_id = source_location.id
        LEFT JOIN
        stock_location dest_location ON sm.location_dest_id = dest_location.id
      WHERE
        sm.state IN ('confirmed', 'assigned', 'waiting') AND
        source_location.usage = 'internal' AND dest_location.usage = 'internal'
      GROUP BY sm.date_expected, sm.product_id, sm.picking_partner_id, sm.partner_id, sm.location_id
      UNION ALL
      SELECT
        MIN(sm.id)              AS id,
        sm.product_id,
        CASE WHEN sm.date_expected > CURRENT_DATE
          THEN to_date(to_char(sm.date_expected, 'YYYY/MM/DD'), 'YYYY/MM/DD')
        ELSE to_date(to_char(CURRENT_DATE, 'YYYY/MM/DD'), 'YYYY/MM/DD') END
                                 AS date,
        SUM(sm.product_qty)   AS product_qty,
        (CASE WHEN sm.picking_partner_id IS NOT NULL
          THEN sm.picking_partner_id
         ELSE sm.partner_id END) AS partner_id,
        sm.location_dest_id           AS location_id
      FROM
        stock_move AS sm
        LEFT JOIN
        product_product ON product_product.id = sm.product_id
        LEFT JOIN
        stock_location source_location ON sm.location_id = source_location.id
        LEFT JOIN
        stock_location dest_location ON sm.location_dest_id = dest_location.id
      WHERE
        sm.state IN ('confirmed', 'assigned', 'waiting') AND
        source_location.usage = 'internal' AND dest_location.usage = 'internal'
      GROUP BY sm.date_expected, sm.product_id, sm.picking_partner_id, sm.partner_id, sm.location_dest_id
     )
       AS MAIN
     LEFT JOIN
     (SELECT DISTINCT date
      FROM
        (
          SELECT CURRENT_DATE AS DATE
          UNION ALL
          SELECT to_date(to_char(sm.date_expected, 'YYYY/MM/DD'), 'YYYY/MM/DD') AS date
          FROM stock_move sm
            LEFT JOIN
            stock_location source_location ON sm.location_id = source_location.id
            LEFT JOIN
            stock_location dest_location ON sm.location_dest_id = dest_location.id
          WHERE
            sm.state IN ('confirmed', 'assigned', 'waiting') AND sm.date_expected > CURRENT_DATE AND
            (dest_location.usage = 'internal'
             OR source_location.usage = 'internal')) AS DATE_SEARCH)
     SUB ON (SUB.date IS NOT NULL)
   GROUP BY MAIN.product_id, SUB.date, MAIN.date, MAIN.partner_id, MAIN.location_id
  ) AS FINAL
  JOIN stock_location on FINAL.location_id = stock_location.id
GROUP BY product_id, date, FINAL.partner_id, FINAL.location_id, warehouse_id)""")


ReportStockForecast()


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    active = fields.Boolean(string='Aktyvus', default=True)
    quant_location_id = fields.Many2one('stock.location', string='Current Location', compute='_location',
                                        compute_sudo=True, store=True)

    @api.one
    @api.depends('quant_ids.location_id')
    def _location(self):
        if self.sudo().quant_ids:
            quant = self.sudo().env['stock.quant'].search([('lot_id', '=', self.id)], order='in_date desc', limit=1)
            self.quant_location_id = quant.location_id.id
        else:
            self.quant_location_id = False

    @api.multi
    @api.constrains('name', 'product_id', 'active')
    def constraint_unique_name(self):
        for rec in self:
            if self.env['stock.production.lot'].sudo().search_count(
                    [('id', '!=', rec.id), ('name', '=', rec.name), ('product_id', '=', rec.product_id.id)]):
                raise exceptions.ValidationError(_('Serijino numerio ir produkto kombinacija privalo būti unikali!'))

    @api.multi
    @api.constrains('product_id', 'quant_ids')
    def constrain_products(self):
        for rec in self:
            if rec.quant_ids.filtered(lambda r: r.product_id != rec.product_id):
                raise exceptions.ValidationError(
                    _('SN ir produkto neatitikimas. Susisiekite su sistemos administratoriumi.')
                )

    @api.multi
    @api.constrains('product_id')
    def constrain_quant_unique(self):
        for rec in self:
            if len(rec.quant_ids) > 1 and rec.product_id.tracking == 'serial':
                raise exceptions.ValidationError(_('Nustatytas ne unikalus SN numeris.'))
            # raise exceptions.ValidationError(
            #     _('Serial numbers must be unique ([%s] %s). It could happen if SN was scanned'
            #       ' in line with wrong package or if wrong location is set. '
            #       'If you believe this is a mistake, please contact support.') % (self.product_id.code, self.name))


StockProductionLot()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.multi
    def action_cancel_invoices(self):
        if self.env.user.has_group('robo_stock.group_purchase_user_all'):
            self = self.sudo()
        invoices = self.mapped('invoice_ids')

        if any([inv.state == 'paid' for inv in invoices]):
            raise exceptions.UserError(
                _('There is at least one invoice that has already been paid. Please cancel invoice first.'))

        for inv in invoices:
            if inv.state not in ['paid', 'cancel']:
                inv.action_invoice_cancel()
            if inv.state == 'cancel' and not inv.move_name:
                inv.unlink()

    @api.multi
    def action_cancel_deliveries(self):
        pickings = self.mapped('picking_ids').filtered(lambda pick: pick.location_id.usage == 'supplier' and
                                                          pick.location_dest_id.usage == 'internal' and
                                                          any([move.non_error_quant_ids for move in pick.move_lines]))  # having non_error_quant_ids implies pick.state == 'done'

        for picking in pickings:
            for move in picking.move_lines:
                if any([q.location_id != picking.location_dest_id for q in move.quant_ids]):
                    raise exceptions.UserError(
                        _('Some items have already been moved and one or more pickings cannot be canceled'))

        for picking in pickings:
            picking_return = self.env['stock.return.picking'].with_context(active_id=picking.id).create(
                {'mistake_type': 'cancel', 'error': True})
            picking_return._create_returns()

    @api.multi
    def button_cancel(self):
        for order in self:
            order.action_cancel_invoices()
            order.action_cancel_deliveries()

            for pick in order.picking_ids:
                if pick.state == 'done' and pick.cancel_state != 'error':
                    raise exceptions.UserError(
                        _('Negalima atšaukti užsakymo %s su neatšauktais važtaraščiais.') % (order.name))
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise exceptions.UserError(
                        _("Negalima atšaukti užsakymo, kuris turi patvirtintų sąskaitų faktūrų."))

            for pick in order.picking_ids.filtered(lambda r: r.state not in ['cancel', 'done']):
                pick.action_cancel()
            # TDE FIXME: I don' think context key is necessary, as actions are not related / called from each other
            if not self.env.context.get('cancel_procurement'):
                procurements = order.order_line.mapped('procurement_ids')
                procurements.filtered(lambda r: r.state not in ('cancel', 'exception') and r.rule_id.propagate).write(
                    {'state': 'cancel'})
                procurements.filtered(
                    lambda r: r.state not in ('cancel', 'exception') and not r.rule_id.propagate).write(
                    {'state': 'exception'})
                moves = procurements.filtered(lambda r: r.rule_id.propagate).mapped('move_dest_id')
                moves.filtered(lambda r: r.state != 'cancel').action_cancel()
        self.mapped('picking_ids').filtered(
            lambda p: p.state == 'done' and p.cancel_state == 'error').mapped('move_lines').filtered(
            lambda m: m.product_id.tracking != 'none').mapped('quant_ids.lot_id').write({'active': False})

        self.write({'state': 'cancel'})


PurchaseOrder()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.multi
    def _get_stock_move_price_unit(self):
        self.ensure_one()
        line = self[0]
        order = line.order_id
        if line.product_qty:
            price_unit = line.price_subtotal / line.product_qty  # P3:DivOK
        else:
            price_unit = 0.0
        if line.product_uom.id != line.product_id.uom_id.id:
            price_unit *= line.product_uom.factor / line.product_id.uom_id.factor  # P3:DivOK
        if order.currency_id != order.company_id.currency_id:
            price_unit = order.currency_id.with_context(date=order.date_planned).compute(price_unit, order.company_id.currency_id, round=False)
        return price_unit
        # return super(PurchaseOrderLine, self.with_context(date=order.date_planned))._get_stock_move_price_unit()


PurchaseOrderLine()


class ProductCategory(models.Model):
    _inherit = 'product.category'

    account_scrap = fields.Many2one('account.account', string='Broko sąnaudų sąskaita')
    robo_category = fields.Boolean(string='Sisteminė kategorija', default=False)
    acc_product_type = fields.Selection([('product', 'Produktas'), ('service', 'Paslauga')],
                                        string='Produktų apskaitos tipas', required=True, default='service')

    @api.model
    def default_get(self, field_list):
        res = super(ProductCategory, self).default_get(field_list)
        res['type'] = 'normal'
        res['property_cost_method'] = 'real'
        res['property_valuation'] = 'real_time'
        if 'parent_id' not in res or not res['parent_id']:
            parent_id = self.env.ref('l10n_lt.product_category_1').id
            res['parent_id'] = parent_id
        return res

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            self.acc_product_type = self.parent_id.acc_product_type
            self.accounting_category_type = self.parent_id.accounting_category_type

    @api.multi
    def unlink(self):
        if any(x.robo_category for x in self):
            raise exceptions.UserError(_('Negalite ištrinti sisteminių kategorijų'))
        return super(ProductCategory, self).unlink()


ProductCategory()


class StockPackOperation(models.Model):
    _inherit = 'stock.pack.operation'

    product_description = fields.Text(string='Aprašymas')

    @api.model
    def create(self, vals):
        pack_id = super(StockPackOperation, self).create(vals)
        if pack_id.product_id:
            moves = pack_id.picking_id.move_lines.filtered(lambda r: r.product_id == pack_id.product_id)
            if moves:
                desc = moves[0].name
            else:
                desc = pack_id.product_id.display_name
                if pack_id.product_id.description_picking:
                    desc += '\n' + pack_id.product_id.description_picking
            pack_id.write({
                'product_description': desc,
            })
        return pack_id

    @api.constrains('qty_done')
    def constraint_qty_done(self):
        for rec in self:
            if tools.float_compare(rec.qty_done, rec.product_qty, precision_digits=dp.get_precision('Product Unit of Measure')(rec._cr)[1]) > 0:
                raise exceptions.ValidationError("You cannot transfer more than planned")


StockPackOperation()
