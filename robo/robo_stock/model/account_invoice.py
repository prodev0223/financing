# -*- coding: utf-8 -*-
from __future__ import division
import logging

from odoo import models, fields, api, _, tools, exceptions


_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def _default_location_id(self):
        """Returns default location - either one set in res.company or earliest location with internal usage"""
        company = self.sudo().env.user.company_id
        default_location = False
        if company.simplified_stock_multi_locations:
            default_location = company.simplified_stock_default_location
            if not default_location:
                default_location = self.env['stock.location'].get_default_location()
        return default_location

    politika_sandelio_apskaita = fields.Selection(
        [('simple', 'Supaprastintas'), ('extended', 'Išplėstinis')], string='Sandėlio apskaitos politika',
        compute='_politika_sandelio_apskaita')
    show_lots = fields.Boolean(string='Rodyti SN numerius', compute='_show_lots')
    show_do_picking_transfer = fields.Boolean(compute='_compute_show_do_picking_transfer')
    num_rel_pickings = fields.Integer(compute='_num_rel_pickings')
    skip_picking_creation = fields.Boolean(string='Nekurti važtaraščių', copy=False, sequence=100)

    required_location_id = fields.Boolean(compute='_compute_required_location_id')
    location_id = fields.Many2one(
        'stock.location', string='Atsargų vieta',
        default=_default_location_id,
        domain="[('usage','=','internal')]",
        inverse='_set_location_id',
    )
    show_stock_moves_not_matching_warning = fields.Boolean(compute='_compute_show_stock_moves_not_matching_warning')
    cost_mismatch = fields.Boolean(
        compute='_compute_cost_mismatch',
        store=True, string='Produktų savikainos neatitikimai',
    )
    picking_done = fields.Boolean(compute='_compute_picking_done', store=True, compute_sudo=True, sequence=100)
    warehouse_cost = fields.Float(string='Warehouse cost')
    warehouse_cost_move_id = fields.Many2one('account.move', string='Warehouse cost move', on_delete='set null')

    @api.multi
    def _set_location_id(self):
        """
        Set default location ID on the lines if there's empty lines
        and it's required on the invoice (occurs when invoice
        is not created from the form view - onchange is not
        triggered)
        :return: None
        """
        # Filter required invoices
        for rec in self.filtered(lambda x: x.required_location_id):
            # Filter lines that have missing locations
            lines = rec.invoice_line_ids.filtered(
                lambda x: x.product_id.type == 'product' and not x.location_id)
            lines.write({'location_id': rec.location_id.id})

    @api.multi
    @api.depends('picking_id', 'picking_id.state', 'invoice_line_ids.product_id', 'picking_id.cancel_state')
    def _compute_picking_done(self):
        """
        Check whether related pickings are done on invoices
        that are confirmed and have stock-able products.
        :return: None
        """
        for rec in self:
            # Skip execution altogether if picking state is not in done/cancel
            if rec.picking_id and rec.picking_id.state not in ['done', 'cancel']:
                continue
            picking_done = True
            if rec.state in ['open', 'paid']:
                # Get related pickings, method filters out error pickings by default
                non_error_pickings = rec.get_related_pickings()
                if non_error_pickings and any(x.state != 'done' for x in non_error_pickings):
                    picking_done = False
                elif not non_error_pickings and not rec.sale_ids and any(
                        x.product_id.type == 'product' for x in rec.invoice_line_ids):
                    picking_done = False
            rec.picking_done = picking_done

    @api.multi
    @api.depends('picking_id.state', 'invoice_line_ids.product_id',
                 'invoice_line_ids.price_subtotal_signed', 'invoice_line_ids.cost')
    def _compute_cost_mismatch(self):
        if self.env.user.sudo().company_id.politika_sandelio_apskaita == 'extended':
            # Loop through invoices that have confirmed pickings
            for rec in self.filtered(lambda x: x.picking_id.state == 'done'):
                cost_mismatch = False
                for line in rec.invoice_line_ids.filtered(lambda x: x.product_id.type == 'product'):
                    # Calculate the difference
                    difference = abs(abs(line.cost) - abs(line.price_subtotal_signed))
                    # if absolute difference is more than 0.1, mark invoice as cost mismatched
                    if tools.float_round(difference, precision_rounding=line.uom_id.rounding) > 0.1:
                        cost_mismatch = True
                        break
                rec.cost_mismatch = cost_mismatch

    @api.multi
    @api.depends('invoice_line_ids', 'invoice_line_ids.product_id')
    def _compute_required_location_id(self):
        """
        Compute //
        Check whether location field in the invoice
        should be required or not
        :return: None
        """
        has_group = self.env.user.has_group('robo_stock.group_simplified_stock_multi_locations')
        for rec in self:
            has_products = any(x.product_id.type == 'product' for x in rec.invoice_line_ids)
            rec.required_location_id = has_group and has_products

    @api.depends('state', 'picking_id')
    def _compute_show_stock_moves_not_matching_warning(self):
        """
        Check whether related stock moves have the same product quantities
        :return: None
        """
        StockMove = self.env['stock.move'].sudo()
        if self.env.user.sudo().company_id.politika_sandelio_apskaita == 'extended':
            for rec in self.filtered(lambda x: x.picking_id):
                for line in rec.invoice_line_ids.filtered(lambda x: x.product_id.type == 'product'):
                    stock_moves = StockMove.search([
                        ('invoice_line_id', '=', line.id),
                        ('picking_id.cancel_state', '!=', 'error'),
                    ])
                    if not stock_moves:
                        continue
                    # Check whether current invoice line product has mapping
                    mapping = line.sudo().product_id.mapping_ids.filtered(
                        lambda r: r.partner_id == line.invoice_id.partner_id
                    )
                    # If current line has mapping and it's invoice type is 'in', filter
                    # the moves with mapped product and do reverse ratio conversion
                    if mapping and line.invoice_id.type == 'in_invoice':
                        # Get the mapped and non mapped moves
                        mapped_moves = stock_moves.filtered(lambda x: x.product_id == mapping.mapped_product_id)
                        non_mapped_moves = stock_moves.filtered(lambda x: x.id not in mapped_moves.ids)

                        # Calculate final, re-mapped quantity
                        qty = sum(x.product_uom_qty / mapping.ratio for x in mapped_moves) + sum(
                            x.product_uom_qty for x in non_mapped_moves)  # P3:DivOK
                    else:
                        qty = sum(x.product_uom_qty for x in stock_moves)

                    if tools.float_compare(qty, line.quantity, precision_rounding=line.uom_id.rounding):
                        rec.show_stock_moves_not_matching_warning = True
                        break

    @api.multi
    def open_related_stock_pickings(self):
        pickings = self.get_related_pickings()

        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'name': 'Susiję važtaraščiai',
            'view_id': False,
            'domain': "[('id', 'in', %s)]" % pickings.ids,
        }

    @api.one
    def _num_rel_pickings(self):
        pickings = self.get_related_pickings()
        self.num_rel_pickings = len(pickings)

    @api.multi
    def _compute_show_create_picking(self):
        """
        ! COMPLETE OVERRIDE OF l10n_lt _compute_show_create_picking !
        Check whether stock picking creation button
        should be shown to the current user
        :return: None
        """
        # Check the states of the invoice
        states = ['open', 'paid']
        if self._context.get('include_draft'):
            states += ['draft']
        # Check if user has the group and whether stock company policy is extended
        extended_stock = self.sudo().env.user.company_id.politika_sandelio_apskaita == 'extended'
        has_groups = self.env.user.has_group('robo_stock.robo_stock_extended') or self.env.user.is_manager()
        for rec in self.filtered(lambda x: x.state in states):
            show_create_picking = False
            # Only allow the creation if user has stock group
            if has_groups and any(ln.product_id.type == 'product' for ln in rec.invoice_line_ids) and extended_stock:
                if not rec.picking_id and not rec.sale_ids \
                        and not rec.invoice_line_ids.filtered(lambda r: r.purchase_id):
                    show_create_picking = True
                else:
                    # Only fetch related pickings here, to save resources
                    pickings = rec.get_related_pickings()
                    if pickings and all(x.state == 'cancel' or x.cancel_state == 'error' for x in pickings):
                        show_create_picking = True
            rec.show_create_picking = show_create_picking

    @api.multi
    def _show_lots(self):
        show_lots = self.env.user.has_group('stock.group_production_lot')
        for rec in self:
            rec.show_lots = show_lots

    @api.depends('company_id')
    def _politika_sandelio_apskaita(self):
        politika_sandelio_apskaita = self.env.user.sudo().company_id.politika_sandelio_apskaita
        for rec in self:
            rec.politika_sandelio_apskaita = politika_sandelio_apskaita

    @api.depends('picking_id', 'picking_id.state')
    def _compute_show_do_picking_transfer(self):
        """
        When company has simple stock enabled, allow the client to transfer invoice related picking
        :return: None
        """
        if self.env.user.sudo().company_id.politika_sandelio_apskaita == 'simple':
            for rec in self:
                rec.show_do_picking_transfer = True if rec.picking_id \
                                                       and rec.picking_id.state not in ['done', 'cancel'] else False

    def _prepare_invoice_line_from_po_line(self, line):
        if line.product_id.purchase_method in ['purchase', 'received_with_adjustment']:
            qty = line.product_qty - line.qty_invoiced
        else:
            qty = line.qty_received - line.qty_invoiced
        if tools.float_compare(qty, 0.0, precision_rounding=line.product_uom.rounding) <= 0:
            qty = 0.0
        taxes = line.taxes_id
        invoice_line_tax_ids = line.order_id.fiscal_position_id.map_tax(taxes)
        invoice_line = self.env['account.invoice.line']
        data = {
            'purchase_line_id': line.id,
            'name': line.order_id.name + ': ' + line.name,
            'origin': line.order_id.origin,
            'uom_id': line.product_uom.id,
            'product_id': line.product_id.id,
            'account_id': invoice_line.with_context(
                {'journal_id': self.journal_id.id, 'type': 'in_invoice'})._default_account(),
            'price_unit': line.order_id.currency_id.compute(line.price_unit, self.currency_id, round=False),
            'quantity': qty,
            'discount': 0.0,
            'account_analytic_id': line.account_analytic_id.id,
            'analytic_tag_ids': line.analytic_tag_ids.ids,
            'invoice_line_tax_ids': invoice_line_tax_ids.ids
        }
        account = invoice_line.get_invoice_line_account('in_invoice', line.product_id, line.order_id.fiscal_position_id,
                                                        self.env.user.company_id)
        if account:
            data['account_id'] = account.id
        return data

    @api.onchange('location_id')
    def onchange_location_id(self):
        """Onchange -- Change line locations if invoice location is changed"""
        for line in self.invoice_line_ids:
            line.location_id = self.location_id

    @api.multi
    def update_latest_product_price(self):
        """
        Update latest product prices using price_unit_tax_excluded from the invoice line.
        Method is called on account_invoice open
        :return: None
        """
        for rec in self.filtered(lambda x: x.state in ['open', 'paid'] and x.type == 'out_invoice'):
            # Loop through lines and update the price
            for line in rec.invoice_line_ids.filtered(lambda x: x.product_id):
                latest_price = line.price_unit_tax_excluded
                # Check whether UOM prices need to be converted
                if line.uom_id != line.product_id.uom_id and not tools.float_is_zero(
                        line.product_id.uom_id.factor, precision_digits=2):
                    latest_price *= line.uom_id.factor / line.product_id.uom_id.factor

                line.product_id.sudo().product_tmpl_id.latest_price = latest_price

    @api.multi
    def create_warehouse_move_cost_id(self):
        self.ensure_one()
        if self.warehouse_cost_move_id:
            raise exceptions.UserError(_('This invoice has existing warehouse cost move'))
        if tools.float_is_zero(self.warehouse_cost, precision_digits=2):
            raise exceptions.UserError(_('There is not warehouse cost'))
        journal_id = self.env['account.journal'].search([('code', '=', 'STJ')])
        account_2040 = self.env.ref('l10n_lt.1_account_195').id
        account_6000 = self.env.ref('l10n_lt.1_account_438').id
        move_line_1 = {
            'name': self.number,
            'account_id': account_2040,
            'debit': 0.0 if self.type == 'out_invoice' else self.warehouse_cost,
            'credit': self.warehouse_cost if self.type == 'out_invoice' else 0.0,
            'journal_id': journal_id.id,
            'partner_id': self.partner_id.id,
            # TODO: check which value should be in analytic_account_id field
            # 'analytic_account_id': line.account_analytic_id.id if line.type == 'sale' else False,
        }
        move_line_2 = {
            'name': self.number,
            'account_id': account_6000,
            'credit': 0.0 if self.type == 'out_refund' else self.warehouse_cost,
            'debit': self.warehouse_cost if self.type == 'out_refund' else 0.0,
            'journal_id': journal_id.id,
            'partner_id': self.partner_id.id,
            # TODO: check which value should be in analytic_account_id field
            # 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
        }
        warehouse_cost_move_id = self.env['account.move'].create({'journal_id': journal_id.id,
                                                                  'date': self.date_invoice,
                                                                  'name': self.number,
                                                                  'state': 'draft',
                                                                  'line_ids': [(0, 0, move_line_1),
                                                                               (0, 0, move_line_2)]})
        warehouse_cost_move_id.post()
        res = self.write({'warehouse_cost_move_id': warehouse_cost_move_id.id})
        return res

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        # skip attachments are passed only systemically
        if not self._context.get('skip_attachments', False):
            self.update_latest_product_price()
        company = self.env.user.sudo().company_id
        for rec in self.sudo():
            if tools.float_compare(rec.warehouse_cost, 0.0, precision_digits=2) > 0:
                rec.create_warehouse_move_cost_id()
        if company.politika_sandelio_apskaita == 'simple' and not self._context.get('skip_picking_creation'):
            for rec in self.sudo().filtered(lambda x: not x.skip_picking_creation):
                # Either take the location from the invoice
                # or use the default location
                location = rec.sudo().location_id
                if not location:
                    location = self.env['stock.location'].get_default_location()
                if not rec.picking_id and not rec.sale_ids and not rec.invoice_line_ids.filtered(
                        lambda r: r.purchase_id):
                    delivery_wizard = self.env['invoice.delivery.wizard'].with_context({
                        'invoice_id': rec.id, }).create({'location_id': location.id, })

                    # Create and confirm delivery
                    delivery_wizard.create_delivery()
                    delivery_wizard.confirm_delivery(check_quantities=True)

        self.invoice_line_ids.force_picking_aml_analytics_prep()
        return res

    @api.multi
    def show_related_accounting_entries(self):
        res = super(AccountInvoice, self).show_related_accounting_entries()
        domain = res.get('domain', [])
        if self.number:
            if self.warehouse_cost_move_id:
                domain = ['|'] + domain + [('move_id', '=', self.warehouse_cost_move_id.id)]
                res['domain'] = domain
        return res

    @api.multi
    def get_related_pickings(self):
        """
        Override the method by adding the option
        that filters out error state pickings.
        :return: picking record-set
        """
        pickings = super(AccountInvoice, self).get_related_pickings()
        if not self._context.get('include_error_pickings'):
            pickings = pickings.filtered(lambda x: x.cancel_state != 'error')
        return pickings

    def do_picking_transfer(self):
        if self.env.user.sudo().company_id.politika_sandelio_apskaita == 'simple':
            for rec in self.sudo().filtered(lambda a: a.picking_id and a.picking_id.state not in ['done', 'cancel']):
                rec.picking_id.action_assign()
                if rec.picking_id.shipping_type == 'return':
                    rec.picking_id.force_assign()
                if rec.picking_id.state == 'assigned':
                    rec.picking_id.do_transfer()
                else:
                    body = []
                    for line in rec.picking_id.move_lines:
                        if line.product_id.qty_available < line.ordered_qty or line.product_id.virtual_available < 0:
                            body.append((
                                line.product_id.name_get()[0][1],
                                line.ordered_qty,
                                line.product_id.qty_available,
                                line.product_id.virtual_available,
                            ))
                    if body:
                        raise exceptions.UserError(_('Neužtenka atsargų šiems produktams:\n') + '\n'.join(
                            _('- Produktas: %s, Užsakyta: %s, Turimas kiekis: %s, Prognozė: %s')
                            % vals for vals in body))
                    else:
                        raise exceptions.UserError(_('Neužtenka atsargų'))

    @api.multi
    def action_invoice_cancel(self):
        res = super(AccountInvoice, self).action_invoice_cancel()
        for rec in self.sudo():
            if rec.warehouse_cost_move_id:
                rec.warehouse_cost_move_id.button_cancel()
                rec.warehouse_cost_move_id.unlink()
        if self.env.user.sudo().company_id.politika_sandelio_apskaita == 'simple':
            if self._context.get('skip_stock', False) and self.env.user.is_accountant():
                return res
            for rec in self.sudo():
                # Gathers related pickings
                pickings = rec.get_related_pickings()
                for picking in pickings:
                    if picking.state == 'done':
                        quant_locations = picking.mapped('move_lines.quant_ids.location_id')
                        if len(quant_locations) > 1 or picking.location_dest_id != quant_locations:
                            raise exceptions.UserError(
                                _('Negalima atšaukti sąskaitos, nes važtaraščio %s inventorius pakeitė savo vietą') % picking.name)
                    try:
                        if picking.state == 'done':
                            return_picking = self.env['stock.return.picking'].with_context(
                                active_id=picking.id, error=True).create({})
                            action = return_picking.with_context(simplified_stock=True).create_returns()
                            if action and 'res_id' in action:
                                backorder_id = self.env['stock.picking'].browse(action['res_id'])
                                if backorder_id.state == 'done' and rec.picking_id == picking:
                                    rec.write({'picking_id': False})
                        else:
                            picking.action_cancel()
                            picking.unlink()
                    except Exception as exc:
                        _logger.info('Failed to cancel invoice picking (ID: %s): %s', (picking.id, str(exc.args)))
                        if self.env.user._is_admin():
                            raise exceptions.UserError(_('Nebegalima atšaukti sąskaitos. %s') % str(exc.args))
                        raise exceptions.UserError(
                            _('Nebegalima atšaukti sąskaitos. Klaida atšaukiant važtaraščius (-į).'))
        return res

    @api.multi
    def unlink(self):
        for rec in self.sudo():
            if rec.picking_id and rec.picking_id.state == 'done':
                raise exceptions.Warning(_('Negalite ištrinti sąskaitos. Kreipkitės į buhalterį.'))
            elif rec.picking_id and rec.picking_id.state != 'done':
                rec.picking_id.action_cancel()
                rec.picking_id.unlink()
        super(AccountInvoice, self).unlink()

    @api.multi
    def action_view_sale_robo(self):
        sale_order = self.sale_ids
        action = self.env.ref('robo_stock.open_robo_sale_orders').read()[0]
        action['context'] = {
            'robo_header': {},
            'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock').id,
        }
        if len(sale_order) == 1:
            action['views'] = [(self.env.ref('robo_stock.robo_sale_order_form').id, 'form')]
            action['res_id'] = sale_order.id
        return action

    @api.multi
    def action_view_purchase_robo(self):
        purchase = self.invoice_line_ids.mapped('purchase_id')
        action = self.env.ref('robo_stock.open_robo_purchase_orders').read()[0]
        action['context'] = {
            'robo_header': {},
            'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock').id,
        }
        if len(purchase) == 1:
            action['views'] = [(self.env.ref('robo_stock.robo_purchase_order_form').id, 'form')]
            action['res_id'] = purchase.id
        return action

    @api.multi
    def action_invoice_paid(self):
        res = super(AccountInvoice, self).action_invoice_paid()
        todo = set()
        for invoice in self:
            for line in invoice.invoice_line_ids:
                for sale_line in line.sale_line_ids:
                    todo.add((sale_line.order_id, invoice.number))
        for (order, name) in todo:
            msg = {
                'body': _("Sąskaita %s nuo %s buvo apmokėta.") % (name, order.partner_id.name),
                'robo_chat': True,
                'client_message': True,
                'priority': 'high',
                'front_message': True,
                'partner_ids': [order.user_id.partner_id.id],
                'action_id': self.env.ref('robo_stock.open_robo_sale_orders').id,
                'rec_model': 'sale.order',
                'rec_id': order.id,
            }
            order.with_context(internal_ticketing=True).sudo().robo_message_post(**msg)
        return res

    @api.multi
    def open_picking(self):
        self.ensure_one()
        picking_ids = self.picking_id
        ids_to_search = picking_ids.ids
        while ids_to_search:
            pickings_to_add = self.env['stock.picking'].search([('backorder_id', 'in', ids_to_search)])
            ids_to_search = pickings_to_add.ids
            picking_ids |= pickings_to_add
        if self._context.get('front_view', False) and self.number:
            pickings_to_add = self.env['stock.picking'].search([('origin', '=', self.number)])
            picking_ids |= pickings_to_add
        if len(picking_ids) == 1:
            action = {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'res_id': self.picking_id.id,
                'view_id': self.env.ref('robo_stock.robo_stock_picking_form').id,
                'type': 'ir.actions.act_window',
                'target': 'current',
            }
        else:
            action = self.env.ref('robo_stock.open_robo_stock_picking').read()[0]
            action['domain'] = [('id', 'in', picking_ids.ids)]
            action['context'] = {
                'robo_header': {},
                'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock_pickings').id,
            }

        return action

    @api.multi
    def open_related_pickings_move_lines(self):
        pickings = self.get_related_pickings()

        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'name': 'Susiję važtaraščių apskaitos įrašai',
            'view_id': False,
            'domain': "[('ref', 'in', %s)]" % pickings.mapped('name'),
        }

    @api.multi
    def button_recompute_picking_done(self):
        """
        Button that allows the user to manually recompute
        picking done on a selected invoice.
        :return: None
        """
        self.ensure_one()
        self._compute_picking_done()

    @api.multi
    def get_extra_private_consumption_values(self):
        """
        Get extra values to set for private consumption move lines
        :return: A dictionary of values to set
        """
        self.ensure_one()
        inventory = self.env['stock.inventory'].search([('invoice_id', '=', self.id), ('state', '=', 'done')], limit=1)

        return {
            'analytic_account_id': inventory.account_analytic_id.id
        }

    @api.model
    def cron_recompute_picking_done(self):
        """
        Manually recomputes picking done on every non-done invoice,
        since the compute method can't depend on every trigger efficiently.
        :return: None
        """
        invoices = self.search([('picking_done', '=', False)])
        invoices._compute_picking_done()
