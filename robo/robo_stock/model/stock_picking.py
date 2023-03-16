# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from odoo.addons.queue_job.job import job
from odoo.addons.robo_basic.models.utils import humanize_number
import logging
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _default_picking_type_id(self):
        return self.env['stock.picking.type'].search([('code', '=', 'internal')], order='id desc', limit=1).id

    state = fields.Selection([
        ('draft', 'Juodraštis'), ('cancel', 'Atšaukta'),
        ('waiting', 'Laukia susijusių operacijų'),
        ('confirmed', 'Trūksta atsargų'),
        ('partially_available', 'Dalinai rezervuota'),
        ('assigned', 'Paruošta išsiuntimui'), ('done', 'Išsiųsta')],
        help="")
    products_inside = fields.Html(compute='_compute_picking_products', store=True, sequence=100)
    picking_type_id = fields.Many2one('stock.picking.type', default=_default_picking_type_id, sequence=100)
    cancel_state = fields.Selection([('non_error', 'Neatšauktas'),
                                     ('partial_error', 'Dalinai atšauktas'),
                                     ('error', 'Atšauktas')],
                                    string='Atšaukimo statusas', compute='_compute_cancel_state', store=True)
    potential_duplicate = fields.Boolean(compute='_compute_potential_duplicate')
    invoice_pdf = fields.Binary(compute='_invoice_pdf')
    num_rel_invoices = fields.Integer(compute='_compute_num_rel_invoices')
    origin = fields.Char(copy=False)

    # FIFO Cost fields
    total_cost = fields.Float(string='Bendra prekių vertė (FIFO)', compute='_compute_total_cost')
    show_total_cost = fields.Boolean(compute='_compute_total_cost')
    # AVG Cost fields
    avg_total_cost = fields.Float(string='Vid. bendra prekių vertė', compute='_compute_total_cost')

    @api.multi
    def _compute_total_cost(self):
        """
        Calculates total moved quant cost for the picking
        :return: None
        """
        for rec in self:
            total_avg = total_fifo = 0.0
            # Check for non error quant records
            if rec.sudo().move_lines:
                self.env.cr.execute(
                    '''SELECT SUM(cost * qty) FROM stock_quant WHERE id IN 
                    (SELECT quant_id FROM non_error_stock_quant_move_rel WHERE move_id in %s)''',
                    (tuple(rec.sudo().move_lines.ids, ),)
                )
                total_fifo = self.env.cr.fetchone()[0] or 0.0
            zero_fifo_qty = tools.float_is_zero(total_fifo, precision_digits=5)
            if zero_fifo_qty and rec.sudo().move_lines:
                # Execute the query to get the total avg amount from reserved quants
                self.env.cr.execute(
                    '''SELECT SUM(cost * qty) FROM stock_quant WHERE reservation_id in %s''',
                    (tuple(rec.sudo().move_lines.ids, ),)
                )
                total_avg = self.env.cr.fetchone()[0] or 0.0
                if tools.float_is_zero(total_avg, precision_digits=5):
                    # If total average is zero, search for non-reserved quants
                    self.env.cr.execute(
                        '''SELECT SUM(cost * qty) FROM stock_quant WHERE id IN 
                        (SELECT quant_id FROM stock_quant_move_rel WHERE move_id in %s)''',
                        (tuple(rec.sudo().move_lines.ids, ),)
                    )
                    total_avg = self.env.cr.fetchone()[0] or 0.0
                # If total average is zero again, just take the cost from the product
                if tools.float_is_zero(total_avg, precision_digits=5):
                    total_avg = sum(x.product_id.avg_cost * x.product_uom_qty for x in rec.sudo().move_lines)

            # Assign the values
            rec.show_total_cost = not zero_fifo_qty
            rec.total_cost = total_fifo
            rec.avg_total_cost = total_avg

    @api.multi
    def _invoice_pdf(self):
        if not self.env.user.has_group('robo_stock.robo_stock_pdf_pickings'):
            return
        for rec in self:
            for invoice in rec.sudo().mapped('move_lines.invoice_line_id.invoice_id'):
                rec.invoice_pdf = invoice.pdf
                break
            for invoice in rec.sudo().mapped('move_lines.purchase_line_id.invoice_lines.invoice_id'):
                rec.invoice_pdf = invoice.pdf
                break

    def _compute_num_rel_invoices(self):
        AccountInvoice = self.env['account.invoice']
        for rec in self:
            related_invoices = AccountInvoice.search([('picking_id', '=', rec.id)])
            if rec.origin:
                related_invoices |= AccountInvoice.search([('number', '=', rec.origin)])
            rec.num_rel_invoices = len(related_invoices)

    @api.multi
    @api.constrains('location_dest_id', 'picking_type_id')
    def _check_picking_type_location_types(self):
        """
        Constraints //
        Check integrity between picking_type_id and location_dest_id
            - If picking type is of internal type, destination location
            must be of internal type as well
        :return: None
        """
        deny_usages = ['supplier', 'customer']
        for rec in self:
            if rec.picking_type_id.code == 'internal' and (
                    rec.location_dest_id.usage in deny_usages or rec.location_id.usage in deny_usages):
                raise exceptions.ValidationError(
                    _('Vidinių pervežimų operacijoms privaloma pasirinkti vidinę lokaciją pakrovimo ir '
                      'pristatymo vietoms!'))

    @api.multi
    def action_picking_return(self):
        """
        Return the action for picking return wizard
        :return:
        """
        self.ensure_one()
        wizard_id = self.env['stock.return.picking'].with_context(active_id=self.id).create(dict())
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.return.picking',
            'view_mode': 'form',
            'view_type': 'form',
            'view_id': self.env.ref('stock.view_stock_return_picking_form').id,
            'target': 'new',
            'res_id': wizard_id.id,
        }

    @api.multi
    @api.depends('location_dest_id', 'origin', 'supplier_note')
    def _compute_potential_duplicate(self):
        for rec in self:
            if rec.location_dest_id and (rec.origin or rec.supplier_note):
                # Prepare base domain and append extra details if they exist on original picking
                domain = [('location_dest_id', '=', rec.location_dest_id.id), ('cancel_state', '!=', 'error')]
                if rec.origin:
                    domain.append(('origin', '=', rec.origin))
                if rec.supplier_note:
                    domain.append(('supplier_note', '=', rec.supplier_note))
                if isinstance(rec.id, (int, long)):
                    domain.append(('id', '!=', rec.id))
                elif rec.name and rec.name != '/':
                    domain.append(('name', '!=', rec.name))
                if self.env['stock.picking'].search_count(domain):
                    rec.potential_duplicate = True

    @api.onchange('min_date')
    def onchange_date(self):
        if self.min_date:
            self.move_lines.write({'date_expected': self.min_date})

    @api.multi
    def recalculate_cancels(self):
        self.ensure_one()
        self.move_lines.calculate_non_error_quants()

    @api.multi
    @api.depends('move_lines.non_error_quant_ids', 'state')
    def _compute_cancel_state(self):
        for rec in self:
            non_error_quants = rec.move_lines.mapped('non_error_quant_ids')
            quants = rec.move_lines.mapped('quant_ids')
            non_error_qty = sum(non_error_quants.mapped('qty'))
            quant_qty = sum(quants.mapped('qty'))
            if rec.state == 'cancel':
                cancel_state = 'error'
            elif not non_error_quants and rec.state == 'done':
                cancel_state = 'error'
            elif rec.state not in ['done', 'cancel']:
                cancel_state = 'non_error'
            elif non_error_quants and tools.float_compare(non_error_qty, quant_qty, precision_digits=5) == 0:
                cancel_state = 'non_error'
            else:
                cancel_state = 'partial_error'
            # Only write the cancel state if it differs
            if cancel_state != rec.cancel_state:
                rec.cancel_state = cancel_state

    @api.multi
    def export_to_i_vaz(self):
        return self.export_to_i_vaz_wizard()

    @api.one
    @api.depends('move_lines.product_id', 'move_lines.product_uom_qty', 'partner_id')
    def _compute_picking_products(self):
        if self.move_lines:
            list_of_products = self.move_lines.filtered(lambda r: r.state != 'cancel').mapped(
                lambda r:
                '<div class="purchase-product-line">'
                + '<span class="purchase-product">'
                + (r.product_id.name or u' ') + u' '
                + ((u'[' + r.product_id.default_code + u'] ') if r.product_id.default_code else u'')
                + '</span>'
                + '<span class="purchase-qty">'
                + (unicode(humanize_number(r.product_uom_qty)) or u' ')
                + '</span>'
                + '</div>'
            )
            if len(list_of_products) > 3:
                list_of_products = list_of_products[:3]
                list_of_products.append('<span>...</span>')

            self.products_inside = ''.join(list_of_products)
        else:
            self.products_inside = ''

    @api.multi
    def do_new_transfer(self):
        for rec in self:
            if rec.picking_type_id.code == 'incoming':
                for pack in rec.pack_operation_product_ids:
                    if pack.product_id.purchase_method == 'received_with_adjustment':
                        if pack.product_qty == 0:  # 0 reiskia prideta nauja eilute, tai nedarom pakeitimu
                            continue
                        if tools.float_compare(pack.product_qty, pack.qty_done, precision_digits=2):
                            diff = pack.qty_done - pack.product_qty
                            for move_link in pack.linked_move_operation_ids:
                                if not diff:
                                    break
                                if move_link.move_id.location_id.usage != 'supplier':
                                    break
                                move_link.move_id.product_uom_qty += diff
                                diff = 0
        res = super(StockPicking, self).do_new_transfer()
        if isinstance(res, dict):
            if 'context' in res:
                ctx = res['context']
                if isinstance(ctx, dict):
                    ctx = ctx.copy()
                    if 'form_view_ref' in ctx:
                        ctx.pop('form_view_ref')
                    res['context'] = ctx
        return res

    @api.multi
    def set_back_to_draft(self):
        self.ensure_one()
        if self.state == 'confirmed':
            self.do_unreserve()
            self.env['stock.pack.operation'].search([('picking_id', '=', self.id)]).unlink()
            self.move_lines.write({'state': 'draft'})

    @api.multi
    def action_view_invoice_robo(self):
        if self.sale_id:
            return self.sale_id.action_view_invoice_robo()
        elif self.purchase_id:
            return self.purchase_id.action_view_invoice_robo()
        else:
            AccountInvoice = self.env['account.invoice']
            related_invoices = AccountInvoice.search([('picking_id', '=', self.id)])
            if self.origin:
                related_invoices |= AccountInvoice.search([('number', '=', self.origin)])

            if not related_invoices:
                return

            if related_invoices[0].type in ['out_invoice', 'out_refund']:
                action = self.env.ref('robo.open_client_invoice')
                view_id = self.env.ref('robo.pajamos_form').id
            else:
                action = self.env.ref('robo.robo_expenses_action')
                view_id = self.env.ref('robo.robo_expenses_form').id

            result = action.read()[0]

            result['context'] = {
                'robo_header': {},
                'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock').id,
            }

            if len(related_invoices) > 1:
                result['domain'] = [('id', 'in', related_invoices.ids)]
            elif len(related_invoices) == 1:
                result['views'] = [(view_id, 'form')]
                result['res_id'] = related_invoices.ids[0]

            return result

    @api.multi
    def _create_backorder(self, backorder_moves=[]):
        res = super(StockPicking, self)._create_backorder(backorder_moves)
        return res

    @api.multi
    def action_view_sale_robo(self):
        sale_order = self.sale_id
        action = self.env.ref('robo_stock.open_robo_sale_orders').read()[0]
        action['context'] = {
            'robo_header': {},
            'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock').id,
        }
        if sale_order:
            action['views'] = [(self.env.ref('robo_stock.robo_sale_order_form').id, 'form')]
            action['res_id'] = sale_order.id
        return action

    @api.multi
    def action_view_purchase_robo(self):
        purchase = self.purchase_id
        action = self.env.ref('robo_stock.open_robo_purchase_orders').read()[0]
        action['context'] = {
            'robo_header': {},
            'robo_menu_name': self.env.ref('robo_stock.menu_robo_stock').id,
        }
        if purchase:
            action['views'] = [(self.env.ref('robo_stock.robo_purchase_order_form').id, 'form')]
            action['res_id'] = purchase.id
        return action

    @api.onchange('picking_type_id', 'partner_id')
    def onchange_picking_type(self):
        if self.picking_type_id:
            if self.picking_type_id.default_location_src_id:
                location_id = self.picking_type_id.default_location_src_id.id
            elif self.partner_id:
                location_id = self.partner_id.property_stock_supplier.id
            else:
                customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

            if self.picking_type_id.default_location_dest_id:
                location_dest_id = self.picking_type_id.default_location_dest_id.id
            elif self.partner_id:
                location_dest_id = self.partner_id.property_stock_customer.id
            else:
                location_dest_id, supplierloc = self.env['stock.warehouse']._get_partner_locations()
            if location_id:
                self.location_id = location_id
            if location_dest_id:
                remove_destination = self.picking_type_id.code == 'internal' and location_id == location_dest_id
                self.location_dest_id = False if remove_destination else location_dest_id
        if self.partner_id:
            if self.partner_id.picking_warn == 'no-message' and self.partner_id.parent_id:
                partner = self.partner_id.parent_id
            elif self.partner_id.picking_warn not in ('no-message', 'block') and self.partner_id.parent_id.picking_warn == 'block':
                partner = self.partner_id.parent_id
            else:
                partner = self.partner_id
            if partner.picking_warn != 'no-message':
                if partner.picking_warn == 'block':
                    self.partner_id = False
                return {'warning': {
                    'title': _('Warning for %s') % partner.name,
                    'message': partner.picking_warn_msg
                }}

    @api.multi
    def action_confirm(self):
        """Override action_confirm by searching for product mappings for move lines"""
        if self._context.get('error'):
            return super(StockPicking, self).action_confirm()
        for rec in self:
            for line in rec.move_lines.filtered(lambda x: x.state == 'draft'):
                # Check whether current move line product can be mapped
                mapping = line.sudo().product_id.mapping_ids.get_mapping(rec.partner_id)
                if mapping:
                    # Update the line if we found related mapping
                    line.update({
                        'product_uom_qty': line.product_uom_qty * mapping.ratio,
                        'product_uom': mapping.mapped_product_id.uom_id.id,
                        'original_product_id': line.product_id.id,
                        'name': mapping.mapped_product_id.name,
                        'product_id': mapping.mapped_product_id.id,
                    })
        return super(StockPicking, self).action_confirm()

    @api.multi
    def confirm_delivery(self, check_quantities=False, invoice=None):
        """
        Assigns and transfers passed pickings.
        Method is moved from the invoice.delivery.wizard
        so it's not wizard bound and can be executed
        from the picking model instead.
        Preserved all of the wizard behaviour
        :param check_quantities: indicates whether quantities should be checked
        :param invoice: related invoice record (preserved wizard behaviour)
        :return: None
        """
        simplified_mode = self.env.user.sudo().company_id.simplified_stock_mode == 'enabled'
        for picking in self.filtered(lambda x: x.state != 'done'):
            picking.action_assign()
            if picking.shipping_type == 'return':
                picking.force_assign()
            if picking.state == 'assigned':
                picking.do_transfer()
            else:
                # Execute extra quantity checks
                if check_quantities and not simplified_mode:
                    body = []
                    for line in picking.move_lines:
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

            # Write picking ID to invoice related landed costs
            if invoice:
                landed_costs = invoice.landed_cost_ids
                landed_costs.write({'picking_ids': [(4, picking.id)]})

    @api.multi
    def do_transfer(self):
        """Override do_transfer by manually recalculating
        Gross Profit of related invoices if any"""
        res = super(StockPicking, self).do_transfer()
        # Calculate gross profit for lines
        records = self.with_context(skip_accountant_validated_check=True)
        records.mapped('invoice_ids.invoice_line_ids')._gp()
        # Calculate gross profit for invoices
        records.mapped('invoice_ids')._gp()
        return res

    @api.multi
    def server_action_confirm_pickings(self):
        """
        Server action called from frontend stock.picking
        tree view, used to confirm multiple pickings.
        If confirmation fails - record is skipped
        :return: None
        """
        for rec in self.filtered(lambda x: x.state == 'draft'):
            try:
                rec.action_confirm()
                self.env.cr.commit()
            except Exception as exc:
                self.env.cr.rollback()
                _logger.info('Multi picking confirm error: {}'.format(exc.args[0]))

    @api.model
    def create_action_confirm_pickings_multi(self):
        """
        Action method, used in stock.picking tree view to
        confirm picking record-set
        :return: None
        """
        action = self.env.ref('robo_stock.action_confirm_pickings_multi')
        if action:
            action.create_action()

    @api.multi
    @job
    def job_do_transfer(self):
        return self.do_transfer()

    @api.multi
    @job
    def job_action_confirm(self):
        return self.action_confirm()

    @api.multi
    @job
    def job_action_assign(self):
        return self.action_assign()
