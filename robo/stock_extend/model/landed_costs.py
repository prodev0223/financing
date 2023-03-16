# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, _, api, tools, exceptions
import odoo.addons.decimal_precision as dp

SPLIT_METHOD = [
    ('equal', 'Equal'),
    ('by_quantity', 'By Quantity'),
    ('by_current_cost_price', 'By Current Cost'),
    ('by_weight', 'By Weight'),
    ('by_volume', 'By Volume'),
]


class StockMove(models.Model):
    _inherit = 'stock.move'

    valuation_adjustment_ids = fields.One2many('stock.valuation.adjustment.lines', 'move_id',
                                               string='Valuation adjustments', readonly=True)


StockMove()


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    valuation_adjustment_ids = fields.Many2many('stock.valuation.adjustment.lines', string='Valuation adjustments',
                                                readonly=True, copy=True, groups='stock.group_stock_manager')


StockQuant()


class StockValuationAdjustmentLines(models.Model):
    _inherit = 'stock.valuation.adjustment.lines'

    unit_cost_change = fields.Float(string='Savikainos pokytis vienetui', lt_string='Savikainos pokytis vienetui',
                                    compute='_unit_cost_change', store=True,
                                    digits=dp.get_precision('Product Unit of Measure'))
    former_cost_per_unit = fields.Float(digits=dp.get_precision('Product Unit of Measure'))
    final_cost = fields.Float(digits=dp.get_precision('Product Unit of Measure'))

    @api.one
    @api.depends('final_cost', 'quantity', 'former_cost_per_unit')
    def _unit_cost_change(self):
        # P3:DivOK
        self.unit_cost_change = (self.final_cost / self.quantity if self.quantity else 1.0) - self.former_cost_per_unit

    @api.constrains('final_cost')
    def _check_final_cost(self):
        """Ensure that quant cost will not be adjusted to negative amount"""
        # Allow the constraint to be skipped from scripts
        if self._context.get('skip_landed_cost_constraints'):
            return
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 2
        for rec in self:
            if tools.float_compare(0.0, rec.final_cost, precision_digits=precision) > 0:
                raise exceptions.ValidationError(_('You cannot adjust the cost to a negative amount!'))


class StockLandedCosts(models.Model):
    _inherit = 'stock.landed.cost'
    _order = 'date DESC'

    mos = fields.Many2many('mrp.production', string='Manufacturing Orders', readonly=True,
                           states={'draft': [('readonly', False)]})
    moves = fields.Many2many('stock.move', string='Stock Moves', compute='_moves', store=True)
    invoice_line_id = fields.Many2one('account.invoice.line', string='Invoice Line', readonly=True)
    invoice_id = fields.Many2one('account.invoice', string='Invoice', readonly=True)
    parent_id = fields.Many2one('stock.landed.cost', string='Source', copy=False)
    related_lc_ids = fields.One2many('stock.landed.cost', 'parent_id', string='Related Landed Costs', copy=False)
    related_lc_number = fields.Integer(string='#Related Landed Costs', compute='_lc_no')
    invoice_partner_id = fields.Many2one('res.partner', string='Paslaugų tiekėjas', lt_string='Paslaugų tiekėjas',
                                         compute='_invoice_partner_id', store=True)
    move_partner_id = fields.Many2one('res.partner', string='Prekių gavėjas/siuntėjas', compute='_move_partner_id',
                                      store=True)

    cancel_id = fields.Many2one('stock.landed.cost', string='Atšaukiamas koregavimas', copy=False)
    cancelled_id = fields.One2many('stock.landed.cost', 'cancel_id', string='Atšaukiantys koregavimai')

    is_reversion = fields.Boolean(compute='_compute_reverts', string='Atšaukiantis koregavimas')
    is_reverted = fields.Boolean(compute='_compute_reverts', string='Atšauktas koregavimas')

    unbuild_ids = fields.Many2many('mrp.unbuild', string='Unbuild orders', readonly=True,
                                   states={'draft': [('readonly', False)]})

    # repair_ids = fields.Many2many('mrp.repair', string='Repairs', readonly=True,
    #                               states={'draft': [('readonly', False)]})

    picking_ids = fields.Many2many('stock.picking', inverse='_set_picking_ids')

    @api.multi
    def _set_picking_ids(self):
        """Sets or re-sets invoices on related landed cost records when picking(s) is/are set"""
        for rec in self:
            invoices = rec.mapped('picking_ids.invoice_ids')
            if not rec.invoice_id and len(invoices) == 1:
                rec.write({'invoice_id': invoices.id})
            if rec.invoice_id and len(invoices) > 1 and (
                    len(rec.picking_ids) > 1 or rec.invoice_id not in invoices):
                rec.write({'invoice_id': False})

    @api.one
    @api.depends('cancel_id', 'cancelled_id')
    def _compute_reverts(self):
        if self.cancel_id:
            self.is_reverted = True
        if self.cancelled_id:
            self.is_reversion = True

    @api.one
    @api.depends('moves.picking_partner_id', 'moves.partner_id')
    def _move_partner_id(self):
        partner_id = self.moves.mapped('picking_partner_id')
        if not partner_id:
            partner_id = self.moves.mapped('partner_id')
        if partner_id:
            self.move_partner_id = partner_id[0].id

    @api.one
    @api.depends('invoice_id.partner_id')
    def _invoice_partner_id(self):
        if self.invoice_id.partner_id:
            self.invoice_partner_id = self.invoice_id.partner_id.id

    @api.one
    @api.depends('related_lc_ids')
    def _lc_no(self):
        if self.related_lc_ids:
            self.related_lc_number = len(self.related_lc_ids)
        else:
            self.related_lc_number = 0

    @api.one
    # @api.depends('mos', 'picking_ids', 'repair_ids')
    @api.depends('mos', 'picking_ids', 'unbuild_ids')
    def _moves(self):
        moves = []
        for picking in self.picking_ids:
            for move in picking.move_lines:
                if move.id not in moves:
                    moves.append(move.id)
        for mo in self.mos:
            for move in mo.move_finished_ids:
                if move.id not in moves:
                    moves.append(move.id)
        for unbuild in self.unbuild_ids:
            for move in unbuild.produce_line_ids:
                if move.id not in moves:
                    moves.append(move.id)

        self.moves = moves

    @api.multi
    def button_revert_landed_cost(self):
        self.ensure_one()
        if self.state != 'done':
            raise exceptions.UserError(_('Galite atšaukti tik patvirtintus koregavimus.'))
        if self.parent_id:
            raise exceptions.UserError(
                _('Galite atšaukti tik susijusį tėvinį koregavimą.'))
        if self.is_reverted:
            raise exceptions.UserError(_('Šis koregavimas jau buvo atšauktas.'))
        vals = {
            'name': self.name + '-R',
            'account_journal_id': self.account_journal_id.id,
            'cost_lines': [(0, 0, {'split_method': line.split_method,
                                   'product_id': line.product_id.id,
                                   'account_id': line.account_id.id,
                                   'price_unit': - line.price_unit,
                                   'name': line.name,
                                   }) for line in self.cost_lines],
            'picking_ids': [(6, 0, self.picking_ids.ids)],
            'mos': [(6, 0, self.mos.ids)],
        }

        lc = self.env['stock.landed.cost'].create(vals)
        lc.compute_landed_cost()
        self.cancel_id = lc.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.landed.cost',
            'res_id': lc.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current',
        }

    @api.multi
    def button_validate(self):
        if self.env.user.has_group('stock.group_stock_manager') \
                or self.env.user.has_group('robo_stock.group_robo_landed_costs'):
            self = self.sudo()
        else:
            raise exceptions.UserError(_('Savikainas koreguoti gali tik sandėlio vadovas ir savikainos koregavimui '
                                         'įgalinti vartotojai.'))
        for cost in self.sudo():
            if cost.moves.filtered(lambda r: r.state != 'done'):
                raise exceptions.UserError(_('Galima koreguoti savikainą tik patvirtintiems važtaraščiams.'))
            if cost.mos and any([mo.state != 'done' for mo in cost.mos]):
                raise exceptions.UserError(_(
                    'Savikainos koregavimas %s negali būti patvirtintas, nes susijęs gamybos užsakymas yra atšauktas.'
                ) % cost.name)
            for line in cost.valuation_adjustment_lines:
                # TODO: Will make it more optimal during the week - quick fix
                # Check whether there's any production quants in the current valuation line
                production_quants = line.move_id.quant_ids.filtered(lambda r: r.location_id.usage == 'production')
                if production_quants:
                    # Get all historical production moves
                    history_production_moves = production_quants.mapped('history_ids').filtered(
                        lambda r: r.location_dest_id.usage == 'production'
                    ).sorted(key=lambda r: r.date, reverse=True)
                    # Optimal amount is 20 for the moment, if actually needed, configuration
                    # parameter can be added, but static value is sufficient for now
                    if len(history_production_moves) > 20:
                        raise exceptions.ValidationError(
                            _('Landed cost cannot be confirmed, related quants are used in more than 20 productions')
                        )
                    # Loop through historical production moves and create landed
                    # costs for them if they still have raw_material_production related
                    for history_production_move in history_production_moves:
                        production = history_production_move.raw_material_production_id
                        if not production:
                            continue
                        # Get related quants
                        related_quants = production_quants.filtered(
                            lambda x: history_production_move in x.history_ids
                        )
                        # Calculate the ratio and additional landed cost
                        ratio = sum(related_quants.mapped('qty')) / line.quantity  # P3:DivOK
                        additional_landed_cost = line.additional_landed_cost * ratio
                        account = production.product_id.categ_id.property_stock_valuation_account_id

                        if not account:
                            product_category = production.product_id.categ_id
                            while product_category and not account:
                                account = product_category.property_stock_valuation_account_id
                                product_category = product_category.parent_id
                        if not account:
                            raise exceptions.ValidationError(
                                _('Neteisingi produkto nustatymai: %s.') % production.product_id.display_name)

                        lc_id = self.create({
                            'account_journal_id': cost.account_journal_id.id,
                            'date': cost.date,
                            'mos': [(4, production.id)],
                            'cost_lines': [(0, 0, {
                                'split_method': line.cost_line_id.split_method,
                                'product_id': line.cost_line_id.product_id.id,
                                'account_id': account.id,
                                'price_unit': additional_landed_cost,
                                'name': line.cost_line_id.name,
                            })],
                        })
                        lc_id.compute_landed_cost()
                        lc_id.button_validate()
                        lc_id.parent_id = cost.id
                    # else:
                    #     if history_production_ids.repair_line_ids.filtered(lambda r: r.type == 'add'):
                    #         related_repair = history_production_ids.repair_line_ids.filtered(lambda r: r.type == 'add')[0].repair_id  # todo ar tikrai taip?
                    #     else:
                    #         related_repair = self.env['mrp.repair'].search([('broken_move_id', '=', history_production_ids.id)], limit=1)
                    #     if related_repair:
                    #         if not related_repair.product_to_make.categ_id.property_stock_valuation_account_id.id:
                    #             raise exceptions.Warning(_('Please configure Stock Valuation Account for product: %s.') % related_repair.product_to_make.display_name)
                    #         lc_id = self.create({
                    #             'account_journal_id': cost.account_journal_id.id,
                    #             'date': cost.date,
                    #             'repair_ids': [(4, related_repair.id)],
                    #             'cost_lines': [(0, 0, {
                    #                 'split_method': line.cost_line_id.split_method,
                    #                 'product_id': line.cost_line_id.product_id.id,
                    #                 'account_id': related_repair.product_to_make.categ_id.property_stock_valuation_account_id.id,
                    #                 'price_unit': additional_landed_cost,
                    #                 'name': line.cost_line_id.name,
                    #             })],
                    #         })
                    #         lc_id.compute_landed_cost()
                    #         lc_id.button_validate()
                    #         lc_id.parent_id = cost.id
                    #     else:
                    #         continue
                    # raise exceptions.UserError(_('You cannot add landed costs to products that were already used in production.'))
        res = super(StockLandedCosts, self).button_validate()
        for unbuild in self.unbuild_ids:
            unbuild.create_prices()
        for cost in self.sudo():
            for line in cost.valuation_adjustment_lines:
                line.move_id.quant_ids.write({'valuation_adjustment_ids': [(4, line.id)]})
        return res

    @api.multi
    def get_valuation_lines(self, move_ids=None):
        lines = []
        if not move_ids:
            return lines

        for move in self.env['stock.move'].browse(move_ids):
            # it doesn't make sense to make a landed cost for a product that isn't set as being valuated in real time at real cost
            if move.product_id.valuation != 'real_time' or move.product_id.cost_method != 'real':
                continue
            total_cost = 0.0
            weight = move.product_id and move.product_id.weight * move.product_qty
            volume = move.product_id and move.product_id.volume * move.product_qty
            for quant in move.quant_ids:
                total_cost += quant.cost * quant.qty
            vals = dict(product_id=move.product_id.id, move_id=move.id, quantity=move.product_qty,
                        former_cost=total_cost, weight=weight, volume=volume)
            lines.append(vals)
        if not lines:
            raise exceptions.UserError(_('Pasirinkti atsargų pervežimai neturi produktų, '
                                         'kurių savikainą būtų galima koreguoti.'))
        return lines

    @api.multi
    def compute_landed_cost(self):
        self.ensure_one()
        line_obj = self.env['stock.valuation.adjustment.lines']
        line_obj.search([('cost_id', 'in', self._ids)]).unlink()
        rounding = self.env.user.company_id.currency_id.rounding
        towrite_dict = {}
        for cost in self:
            if not cost.moves:
                continue
            move_ids = [p.id for p in cost.moves]
            total_qty = 0.0
            total_cost = 0.0
            total_weight = 0.0
            total_volume = 0.0
            total_line = 0.0
            vals = self.get_valuation_lines(move_ids=move_ids)
            for v in vals:
                for line in cost.cost_lines:
                    v.update({'cost_id': cost.id, 'cost_line_id': line.id})
                    line_obj.create(v)
                total_qty += v.get('quantity', 0.0)
                total_cost += v.get('former_cost', 0.0)
                total_weight += v.get('weight', 0.0)
                total_volume += v.get('volume', 0.0)
                total_line += 1

            for line in cost.cost_lines:
                value_split = 0.0
                for valuation in cost.valuation_adjustment_lines:
                    value = 0.0
                    if valuation.cost_line_id and valuation.cost_line_id.id == line.id:
                        if line.split_method == 'by_quantity' and total_qty:
                            per_unit = (line.price_unit / total_qty)  # P3:DivOK
                            value = valuation.quantity * per_unit
                        elif line.split_method == 'by_weight' and total_weight:
                            per_unit = (line.price_unit / total_weight)  # P3:DivOK
                            value = valuation.weight * per_unit
                        elif line.split_method == 'by_volume' and total_volume:
                            per_unit = (line.price_unit / total_volume)  # P3:DivOK
                            value = valuation.volume * per_unit
                        elif line.split_method == 'equal':
                            value = (line.price_unit / total_line)  # P3:DivOK
                        elif line.split_method == 'by_current_cost_price' and total_cost:
                            per_unit = (line.price_unit / total_cost)  # P3:DivOK
                            value = valuation.former_cost * per_unit
                        else:
                            value = (line.price_unit / total_line)  # P3:DivOK

                        if rounding:
                            value = tools.float_round(value, precision_rounding=rounding, rounding_method='UP')
                            fnc = min if line.price_unit > 0 else max
                            value = fnc(value, line.price_unit - value_split)
                            value_split += value

                        if valuation.id not in towrite_dict:
                            towrite_dict[valuation.id] = value
                        else:
                            towrite_dict[valuation.id] += value
        if towrite_dict:
            for key, value in towrite_dict.items():
                line_obj.browse(key).write({'additional_landed_cost': value})
        return True

    @api.model
    def _create_accounting_entries(self, line, move_id, qty_out):
        product_obj = self.env['product.template']
        cost_product = line.cost_line_id and line.cost_line_id.product_id
        if not cost_product:
            return False
        accounts = product_obj.browse(line.product_id.product_tmpl_id.id).get_product_accounts()
        debit_account_id = accounts.get('stock_valuation', False) and accounts['stock_valuation'].id or False
        already_out_account_id = accounts['stock_output'].id
        credit_account_id = line.cost_line_id.account_id.id or cost_product.property_account_expense_id.id or cost_product.categ_id.property_account_expense_categ_id.id

        if not credit_account_id:
            raise exceptions.UserError(
                _('Neteisingi produkto nustatymai: %s.') % cost_product.name)

        if qty_out:
            smove_id = line.move_id
            quant_ids = smove_id.quant_ids.filtered(lambda r: r.location_id.usage != 'internal')
            quant_qtys = {False: 0.0}
            for quant in quant_ids:
                acc_dest = False
                history_ids = quant.history_ids.sorted(key=lambda r: r.date, reverse=True)
                stock_move_id = history_ids[0]
                if stock_move_id.inventory_id.account_id:
                    acc_dest = stock_move_id.inventory_id.account_id.id
                if acc_dest in quant_qtys:
                    quant_qtys[acc_dest] += quant.qty
                else:
                    quant_qtys[acc_dest] = quant.qty

            if tools.float_compare(qty_out, sum(quant_qtys.values()), precision_digits=2) != 0:
                raise exceptions.UserError(_('Nesutampa kiekiai. Kreipkitės į buhalterį.'))

            for acc_dest, qty in quant_qtys.items():
                if qty == 0.0:
                    continue
                out_account = acc_dest if acc_dest else already_out_account_id
                self._create_account_move_line(line, move_id, credit_account_id, debit_account_id, qty, out_account)
        else:

            return self._create_account_move_line(line, move_id, credit_account_id, debit_account_id, qty_out,
                                                  already_out_account_id)

    @api.model
    def create_default_journal(self):
        journal_obj = self.env['account.journal']
        if journal_obj.search_count([('code', '=', 'LC'), ('type', '=', 'general')]) >= self.env[
            'res.company'].search_count([]):
            return
        else:
            for company in self.env['res.company'].search([]):
                if not journal_obj.search_count(
                        [('code', '=', 'LC'), ('type', '=', 'general'), ('company_id', '=', company.id)]):
                    journal_id = self.env['account.journal'].create({
                        'code': 'LC',
                        'type': 'general',
                        'name': 'Landed Costs',
                        'company_id': company.id,
                        'show_on_dashboard': False,
                    })
                    self.env['ir.values'].set_default('stock.landed.cost', 'account_journal_id', journal_id.id,
                                                      company_id=company.id)

    @api.multi
    def action_view_related_lc(self):
        return {
            'name': _('Susiję savikainos koregavimai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'stock.landed.cost',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('parent_id', '=', self.id)],
        }

    @api.multi
    def action_view_origin_lc(self):
        return {
            'name': _('Atšauktas koregavimas'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'stock.landed.cost',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('cancel_id', '=', self.id)],
        }

    @api.multi
    def action_view_reverse_lc(self):
        return {
            'name': _('Atšaukiantis koregavimas'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'stock.landed.cost',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('cancelled_id', '=', self.id)],
        }


StockLandedCosts()


class StockLandedCostsReport(models.Model):
    _name = 'stock.landed.costs.report'
    _auto = False

    quant_id = fields.Many2one('stock.quant', string='Quant')
    lot_id = fields.Many2one('stock.production.lot', string='Lot')
    date = fields.Date(string='Date')
    picking_id = fields.Many2one('stock.picking', string='Stock picking')
    product_id = fields.Many2one('product.product', string='Product')
    cost = fields.Float(string='Current unit cost', group_operator='quantity')
    former_cost_per_unit = fields.Float(string='Former unit cost', group_operator='quantity')
    added_cost = fields.Float(string='Cost change', group_operator='quantity')
    additional_landed_cost = fields.Float(string='Landed costs')
    landed_product_id = fields.Many2one('product.product', string='Landed costs type')
    split_method = fields.Selection(SPLIT_METHOD, string='Split method', sequence=100)
    quantity = fields.Float(string='Quantity')
    val_id = fields.Many2one('stock.valuation.adjustment.lines', string='Valuation line')
    location_id = fields.Many2one('stock.location', string='Location')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'stock_landed_costs_report')
        self._cr.execute('''
        CREATE OR REPLACE VIEW stock_landed_costs_report AS (
        SELECT
            ROW_NUMBER() OVER (ORDER BY stock_quant.id ASC) AS id,
            stock_picking.id as picking_id,
            stock_valuation_adjustment_lines.id AS val_id,
            stock_quant.id as quant_id,
            stock_quant.lot_id,
            stock_move.id as move_id,
            stock_quant.product_id,
            stock_quant.cost,
            stock_valuation_adjustment_lines.former_cost_per_unit,
            stock_valuation_adjustment_lines.additional_landed_cost,
            stock_landed_cost_lines.product_id as landed_product_id,
            stock_landed_cost_lines.split_method,
            stock_valuation_adjustment_lines.quantity,
            stock_valuation_adjustment_lines.unit_cost_change as added_cost,
            stock_landed_cost.date, stock_quant.location_id
        FROM stock_quant
            LEFT JOIN stock_quant_stock_valuation_adjustment_lines_rel ON stock_quant.id = stock_quant_stock_valuation_adjustment_lines_rel.stock_quant_id
            LEFT JOIN stock_valuation_adjustment_lines ON stock_quant_stock_valuation_adjustment_lines_rel.stock_valuation_adjustment_lines_id = stock_valuation_adjustment_lines.id
            LEFT JOIN stock_move ON stock_valuation_adjustment_lines.move_id = stock_move.id
            LEFT JOIN stock_picking ON stock_move.picking_id = stock_picking.id
            LEFT JOIN stock_landed_cost_lines ON stock_valuation_adjustment_lines.cost_line_id = stock_landed_cost_lines.id
            LEFT JOIN stock_landed_cost ON stock_landed_cost.id = stock_valuation_adjustment_lines.cost_id
            LEFT JOIN stock_location ON stock_quant.location_id = stock_location.id
        WHERE stock_valuation_adjustment_lines.id is not null
        ORDER BY stock_quant.id, stock_valuation_adjustment_lines.id, stock_quant.product_id)
        ''')


StockLandedCostsReport()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    landed_cost_ids = fields.Many2many('stock.landed.cost', string='Landed costs', copy=False, sequence=100)

    @api.multi
    def invoice_validate(self):
        lc_obj = self.sudo().env['stock.landed.cost']
        for invoice in self.sudo():
            if invoice.type not in ['in_invoice', 'in_refund']:
                continue

            # Collect related pickings
            related_pickings = invoice.picking_id | invoice.sale_ids.mapped('picking_ids') | invoice.mapped(
                'invoice_line_ids.purchase_id').picking_ids
            if invoice.number:
                related_pickings |= self.env['stock.picking'].search([('origin', '=', invoice.number)])

            landed_cost_ids = []
            for line in invoice.invoice_line_ids:
                if line.landed_cost_id:
                    continue
                if line.product_id.landed_cost_ok:
                    journal_id = self.env['account.journal'].search(
                        [('code', '=', 'LC'), ('company_id', '=', invoice.company_id.id)], limit=1)
                    if not journal_id:
                        journal_id = invoice.journal_id
                    lc_id = lc_obj.create({
                        'date': invoice.date,
                        'account_journal_id': journal_id.id,
                        'picking_ids': [(6, 0, related_pickings.ids)],
                        'invoice_line_id': line.id,
                        'invoice_id': invoice.id,
                        'cost_lines': [(0, 0, {
                            'product_id': line.product_id.id,
                            'name': line.name,
                            'account_id': line.account_id.id,
                            'price_unit': line.price_subtotal_signed,
                            'split_method': line.product_id.split_method,
                        })]
                    })
                    lc_id.compute_landed_cost()
                    landed_cost_ids.append(lc_id.id)
                    line.landed_cost_id = lc_id.id
            if landed_cost_ids:
                invoice.landed_cost_ids = landed_cost_ids
        return super(AccountInvoice, self).invoice_validate()

    # @api.multi
    # def action_cancel(self):
    #     for invoice in self.sudo():
    #         for lc_id in invoice.landed_cost_ids:
    #             if lc_id.account_move_id:
    #                 lc_id.account_move_id.button_cancel()
    #                 lc_id.account_move_id.unlink()
    #                 lc_id.state = 'draft'
    #     return super(AccountInvoice, self).action_cancel()

    @api.multi
    def unlink(self):
        for invoice in self.sudo():
            if invoice.landed_cost_ids:
                invoice.landed_cost_ids.filtered(lambda r: r.state == 'draft').unlink()
        return super(AccountInvoice, self).unlink()

    @api.multi
    def action_invoice_cancel(self):
        if not self.env.user.is_accountant() and \
                self.sudo().mapped('invoice_line_ids.sale_line_ids.order_id').filtered(lambda r: r.state == 'done'):  #somehow .sale_ids is empty
            raise exceptions.UserError(
                _('Negalima atšaukti sąskaitos, kai pardavimo užsakymas jau užrakintas. Pirmiau atrakinkite užsakymą.'))
        return super(AccountInvoice, self).action_invoice_cancel()

    @api.multi
    def get_related_pickings(self):
        """
        Gathers related pickings -> take stock moves
        that are related to the invoice lines
        and map them to get the full picking set
        :return: picking record-set
        """
        self.ensure_one()
        pickings = self.picking_id
        # 1: Get pickings from stock moves
        stock_moves = self.env['stock.move'].search(
            [('invoice_line_id', 'in', self.invoice_line_ids.ids)])
        pickings |= stock_moves.mapped('picking_id')
        # 2: Get pickings from related sales/purchases
        pickings |= self.sale_ids.mapped('picking_ids') | self.mapped(
            'invoice_line_ids.purchase_id.picking_ids')
        # 3: Get pickings by origin
        if self.number:
            pickings |= self.env['stock.picking'].search([('origin', '=', self.number)])
        return pickings

