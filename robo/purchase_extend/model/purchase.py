# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime
from odoo.tools import float_compare


class PurchaseOrder(models.Model):

    _inherit = 'purchase.order'

    @api.model_cr
    def init(self):
        pos_without_location = self.env['purchase.order'].search([('location_dest_id', '=', False)])
        for po in pos_without_location.filtered(lambda r: len(r.picking_ids) > 0):
            location_dest_id = po.picking_ids[0].location_dest_id.id
            po.location_dest_id = location_dest_id
        for po in pos_without_location.filtered(lambda r: len(r.picking_ids) == 0):
            if po.picking_type_id:
                if po.picking_type_id.warehouse_id:
                    location_dest_id = po.picking_type_id.warehouse_id.lot_stock_id.id
                elif po.default_location_dest_id:
                    location_dest_id = po.picking_type_id.default_location_dest_id.id
                else:
                    location_dest_id = False
                if location_dest_id:
                    po.location_dest_id = location_dest_id

    location_dest_id = fields.Many2one('stock.location', string='Pristatymo vieta', lt_string='Pristatymo vieta',
                                       required=True,
                                       states={'sent': [('readonly', True)],
                                               'to approve': [('readonly', True)],
                                               'purchase': [('readonly', True)],
                                               'done': [('readonly', True)],
                                               'cancel': [('readonly', True)],
                                               })

    picking_type_id = fields.Many2one('stock.picking.type', compute='_picking_type_id', store=True)
    reversed = fields.Boolean(string='Grąžinimas', readonly=True, copy=False)
    amount_total_signed = fields.Float(string='Viso suma (EUR)', compute='_amount_total_signed')
    show_signed = fields.Boolean(compute='_show_signed')
    show_vat = fields.Boolean(compute='_show_vat')

    @api.one
    @api.depends('name', 'company_id', 'date_order')
    def _show_vat(self):
        self.show_vat = self.company_id.sudo().with_context({'date': self.date_order}).vat_payer

    @api.onchange('show_vat')
    def set_reset_tax_line_ids(self):
        self.order_line._compute_tax_id()

    @api.multi
    def _create_picking(self):
        stock_picking = self.env['stock.picking']
        for order in self:
            if 'product' in order.order_line.mapped('product_id.type'):
                location_grouping = {}

                for line in order.order_line:
                    if line.location_dest_id in location_grouping:
                        location_grouping[line.location_dest_id].append(line.id)
                    else:
                        location_grouping[line.location_dest_id] = [line.id]

                for location_dest_id, line_ids in location_grouping.items():

                    pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel') and
                                                                    x.location_dest_id == location_dest_id)
                    if not pickings:
                        res = order._prepare_picking()
                        res['location_dest_id'] = location_dest_id.id
                        picking = stock_picking.create(res)
                    else:
                        picking = pickings[0]

                    moves = self.env['purchase.order.line'].browse(line_ids)._create_stock_moves(picking)
                    moves = moves.filtered(lambda x: x.state not in ('done', 'cancel')).action_confirm()
                    moves.force_assign()
                    picking.message_post_with_view('mail.message_origin_link',
                                                   values={'self': picking, 'origin': order},
                                                   subtype_id=self.env.ref('mail.mt_note').id)
        return True

    @api.one
    @api.depends('currency_id')
    def _show_signed(self):
        if self.env.user.sudo().company_id.currency_id.id != self.currency_id.id:
            self.show_signed = True
        else:
            self.show_signed = False

    @api.one
    @api.depends('amount_total', 'currency_id', 'date_order')
    def _amount_total_signed(self):
        if self.currency_id and self.currency_id.id != self.env.user.sudo().company_id.currency_id.id:
            company_currency_id = self.env.user.sudo().company_id.currency_id
            self.amount_total_signed = self.currency_id.with_context(date=self.date_order).compute(self.amount_total,
                                                                                                   company_currency_id,
                                                                                                   round=False)
        else:
            self.amount_total_signed = self.amount_total

    @api.onchange('location_dest_id')
    def change_destination_order_lines(self):
        for line in self.order_line:
            line.location_dest_id = self.location_dest_id

    @api.model
    def _needaction_domain_get(self):
        return [('state', '=', 'draft')]

    @api.multi
    def action_view_invoice(self):
        res = super(PurchaseOrder, self).action_view_invoice()
        if self.partner_ref:
            res['context']['default_reference'] = self.partner_ref
        if self.date_order:
            date_invoice = datetime.strptime(self.date_order, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            res['context']['default_date_invoice'] = date_invoice
        if self.currency_id:
            res['context']['default_currency_id'] = self.currency_id.id
            res['context']['leave_currency'] = True
        return res

    @api.depends('date_order')
    def _compute_date_planned(self):
        for rec in self:
            rec.date_planned = rec.date_order

    @api.one
    @api.depends('location_dest_id')
    def _picking_type_id(self):
        if not self.location_dest_id:
            self.picking_type_id = False
        else:
            warehouse = self.location_dest_id.warehouse_id
            if warehouse:
                picking_type = self.env['stock.picking.type'].search([('code', '=', 'incoming'), ('warehouse_id', '=', warehouse.id)], limit=1)
            else:
                picking_type = False
            if picking_type:
                self.picking_type_id = picking_type.id
            else:
                self.picking_type_id = False

    @api.multi
    def _get_destination_location(self):
        self.ensure_one()
        if self.location_dest_id:
            return self.location_dest_id.id
        return super(PurchaseOrder, self)._get_destination_location()

    @api.multi
    def reverse_po(self):
        for rec in self:
            rec.reverse_pickings()
            rec.reverse_invoices()
            rec.write({'state': 'cancel'})
            rec.reversed = True

    @api.multi
    def reverse_pickings(self):
        def get_moves_to_reverse(move):
            additional_moves_to_reverse = []
            if move.move_dest_id:
                additional_moves_to_reverse.append(move.move_dest_id)
            for reverse_move in move.returned_move_ids:
                additional_moves_to_reverse.extend(get_moves_to_reverse(reverse_move))
            additional_moves_to_reverse.append(move)
            return additional_moves_to_reverse

        moves_to_reverse = []
        for move in self.mapped('picking_ids.move_lines'):
            moves_to_reverse.extend(get_moves_to_reverse(move))

        pickings_to_reverse_ids = []
        for move in moves_to_reverse:  # we want to preserve the order
            if move.picking_id.id not in pickings_to_reverse_ids:
                pickings_to_reverse_ids.append(move.picking_id.id)
        pickings_to_inverse = self.env['stock.picking'].browse(pickings_to_reverse_ids)
        for picking in pickings_to_inverse:
            if picking.state not in ['done', 'cancel']:
                picking.action_cancel()
            elif picking.state == 'done':
                picking_lines = []
                for move in picking.move_lines:
                    return_line = {'product_id': move.product_id.id,
                                   'quantity': move.product_qty,
                                   'move_id': move.id}
                    picking_lines.append((0, 0, return_line))
                return_wiz = self.env['stock.return.picking'].with_context(active_id=picking.id).create(
                    {'product_return_moves': picking_lines,
                     'original_location_id': move.location_dest_id.id,
                     'location_id': move.location_id.id,
                     'error': True})
                reverse_picking_id, reverse_picking_type_id = return_wiz._create_returns()
                reverse_picking = self.env['stock.picking'].browse(reverse_picking_id)
                reverse_picking.do_transfer()

    @api.multi
    def reverse_invoices(self):
        for purchase in self:
            for invoice in purchase.invoice_ids:
                state = invoice.state
                if state not in ['paid', 'cancel']:
                    invoice.signal_workflow('invoice_cancel')
                elif state == 'paid':
                    raise exceptions.Warning(_('Negalite atšaukti pirkimo užsakymo, kuomet susijusios sąskaitos yra apmokėtos.'))


PurchaseOrder()


class PurchaseOrderLine(models.Model):

    _inherit = 'purchase.order.line'

    qty_received = fields.Float(compute='_compute_qty_received_with_reverse', store=True)
    price_unit = fields.Float(inverse='_check_delivered')
    location_dest_id = fields.Many2one('stock.location', string='Pristatymo vieta', lt_string='Pristatymo vieta', required=True)

    @api.multi
    def _create_stock_moves(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        for line in self:
            if line.product_id.type not in ['product']:
                continue
            qty_delivered = 0.0
            price_unit = line._get_stock_move_price_unit()
            for move in line.move_ids.filtered(lambda x: x.state != 'cancel'):
                if move.location_dest_id == line.location_dest_id:
                    qty_delivered += move.product_qty
                elif move.location_id == line.location_dest_id:
                    qty_delivered -= move.product_qty
            template = {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom.id,
                'date': line.order_id.date_order,
                'date_expected': line.date_planned,
                'location_id': line.order_id.partner_id.property_stock_supplier.id,
                'location_dest_id': line.location_dest_id.id,
                'picking_id': picking.id,
                'partner_id': line.order_id.dest_address_id.id,
                'move_dest_id': False,
                'state': 'draft',
                'purchase_line_id': line.id,
                'company_id': line.order_id.company_id.id,
                'price_unit': price_unit,
                'picking_type_id': line.order_id.picking_type_id.id,
                'group_id': line.order_id.group_id.id,
                'procurement_id': False,
                'origin': line.order_id.name,
                'route_ids': line.order_id.picking_type_id.warehouse_id and [
                    (6, 0, [x.id for x in line.order_id.picking_type_id.warehouse_id.route_ids])] or [],
                'warehouse_id': line.order_id.picking_type_id.warehouse_id.id,
            }
            # Fullfill all related procurements with this po line
            diff_quantity = line.product_qty - qty_delivered
            for procurement in line.procurement_ids:
                # If the procurement has some moves already, we should deduct their quantity
                sum_existing_moves = sum(x.product_qty for x in procurement.move_ids if x.state != 'cancel')
                existing_proc_qty = procurement.product_id.uom_id._compute_quantity(sum_existing_moves,
                                                                                    procurement.product_uom)
                procurement_qty = procurement.product_uom._compute_quantity(procurement.product_qty,
                                                                            line.product_uom) - existing_proc_qty
                if float_compare(procurement_qty, 0.0,
                                 precision_rounding=procurement.product_uom.rounding) > 0 and float_compare(
                        diff_quantity, 0.0, precision_rounding=line.product_uom.rounding) > 0:
                    tmp = template.copy()
                    tmp.update({
                        'product_uom_qty': min(procurement_qty, diff_quantity),
                        'move_dest_id': procurement.move_dest_id.id,
                    # move destination is same as procurement destination
                        'procurement_id': procurement.id,
                        'propagate': procurement.rule_id.propagate,
                    })
                    done += moves.create(tmp)
                    diff_quantity -= min(procurement_qty, diff_quantity)
            if float_compare(diff_quantity, 0.0, precision_rounding=line.product_uom.rounding) > 0:
                template['product_uom_qty'] = diff_quantity
                done += moves.create(template)
        return done

    @api.depends('order_id.state', 'move_ids.state', 'move_ids.returned_move_ids.state', 'move_ids.returned_move_ids.returned_move_ids.state',
                 'move_ids.returned_move_ids.returned_move_ids.returned_move_ids.state')
    def _compute_qty_received_with_reverse(self):

        def get_received_qty(move):
            res = 0
            if move.state == 'done':
                res += move.product_qty
            for reverse_move in move.returned_move_ids:
                res -= get_received_qty(reverse_move)
            return res

        for line in self:
            if line.order_id.state not in ['purchase', 'done']:
                line.qty_received = 0.0
                continue
            if line.product_id.type not in ['consu', 'product']:
                line.qty_received = line.product_qty
                continue
            total = 0.0

            for move in line.move_ids:
                total += get_received_qty(move)
            line.qty_received = total

    @api.onchange('taxes_id')
    def onchange_tax_ids(self):
        if self.taxes_id and self.taxes_id.mapped('child_tax_ids'):
            vals = []
            for tax_id in self.taxes_id:
                vals.append((4, tax_id.id))
            for child_id in self.taxes_id.mapped('child_tax_ids'):
                vals.append((4, child_id.id))
            self.taxes_id = vals

    @api.one
    def _check_delivered(self):
        if self.move_ids.filtered(lambda r: r.state == 'done').mapped('non_error_quant_ids'):
            raise exceptions.UserError(
                _('Jau buvo pristatytų judėjimų, todėl negalite keisti savikainos. Pirmiau atšaukite važtaraščius'))

    def get_rounded_price_unit(self, values):
        price_unit = values.get('price_unit', 0.0)
        quantity = values.get('product_qty', 0.0)
        digits = self.env['decimal.precision'].precision_get('Product Price')

        if digits:
            price = tools.float_round(price_unit * quantity, precision_digits=digits)
        else:
            curr_id = values.get('currency_id', False)
            curr = self.env['res.currency'].browse(curr_id)
            if not curr:
                curr_id = values['order_id']['currency_id']
                curr = self.env['res.currency'].browse(curr_id)
            if not curr:
                curr = self.env.user.company_id.currency_id
            price = curr.round(price_unit * quantity)

        price_unit = price / quantity if quantity else price_unit
        return price_unit

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        price_unit_changed = False
        if (isinstance(field_name, basestring) and field_name in ['price_unit', 'product_qty'] or
                isinstance(field_name, list) and any([i in field_name for i in ['price_unit', 'product_qty']])):
            price_unit_changed = True
            price_unit = self.get_rounded_price_unit(values)
            values.update({'price_unit': price_unit})
        res = super(PurchaseOrderLine, self).onchange(values, field_name, field_onchange)
        if price_unit_changed:
            res['value'].setdefault('price_unit', price_unit)
        return res

    #todo: we have two functions with @api.onchange('product_id'). Should we merge ?
    @api.onchange('product_id')
    def onchange_product_id(self):
        res = super(PurchaseOrderLine, self).onchange_product_id()
        # Will override changes made by default by _on_change_quantity() (e.g. seller delay)
        if self.product_id:
            self.date_planned = self.order_id.date_order
        return res

    @api.onchange('product_id')
    def onchange_product_id_fp(self):
        self._compute_tax_id()

    @api.depends('invoice_lines.invoice_id.state')
    def _compute_qty_invoiced(self):
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                if inv_line.invoice_id.state not in ['cancel']:
                    if inv_line.product_id == line.product_id:
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                    else:
                        # We can't really handle lines with different products and different Uom, so this is sketchy but
                        # we avoid errors. For example, it is necessary so you can move back an invoice to draft if you
                        # changed the purchase order line
                        qty += inv_line.uom_id.with_context(**{'raise-exception': False})._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_invoiced = qty


PurchaseOrderLine()
