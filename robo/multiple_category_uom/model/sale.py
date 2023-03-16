# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from odoo.tools import float_is_zero
import odoo.addons.decimal_precision as dp


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    secondary_uom_id = fields.Many2one('product.uom', string='Antrinis matavimo vienetas',
                                       inverse='_set_product_qty_from_secondary')
    secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais',
                                     inverse='_set_product_qty_from_secondary')
    secondary_uom_domain = fields.Many2many('product.uom', string='Leidžiami matavimo vienetai',
                                            compute='_secondary_uom_domain')
    secondary_uom_price_unit = fields.Float(string='Vieneto kaina antriniais matavimo vienetais',
                                            inverse='_set_product_qty_from_secondary',
                                            # digits=dp.get_precision('Product Price')
                                            )
    price_unit = fields.Float(digits=dp.get_precision('Product Price'))

    product_uom_qty = fields.Float(compute='_set_qty_from_secondary_uom_id_qty', default=0.0, digits=(16, 16))

    @api.one
    @api.depends('product_id')
    def _secondary_uom_domain(self):
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

    def set_price_unit_from_secondary(self):
        if self.price_subtotal_make_force_step:
            self.price_unit = self.price_subtotal_save_force_value / self.product_uom_qty \
                if self.product_uom_qty else 0.0
        elif self.secondary_uom_id and self.product_uom and self.product_id:
            self.price_unit = self.product_id.product_tmpl_id.compute_price_from_secondary_uom(
                self.secondary_uom_price_unit,
                self.secondary_uom_id,
                self.product_uom)
        elif not self.product_id and self.secondary_uom_id:
            self.price_unit = self.secondary_uom_price_unit

    @api.one
    def _set_product_qty_from_secondary(self):
        self.compute_main_product_qty()
        self.set_price_unit_from_secondary()

    @api.one
    @api.depends('secondary_uom_id', 'secondary_uom_qty', 'order_id.partner_id', 'product_uom', 'product_id')
    def _set_qty_from_secondary_uom_id_qty(self):
        # copy of compute_main_product_qty method
        if self.secondary_uom_id and self.product_uom and self.product_id:
            self.product_uom_qty = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                              self.secondary_uom_id,
                                                                                              self.product_uom)
        elif not self.secondary_uom_id and self.product_uom and not tools.float_is_zero(self.secondary_uom_qty,
                                                                                        precision_rounding=self.product_uom.rounding):
            self.product_uom_qty = self.secondary_uom_qty

    @api.onchange('secondary_uom_id', 'secondary_uom_price_unit')
    def onch_secondary_uom_id_price(self):
        self.set_price_unit_from_secondary()

    @api.multi
    def _prepare_invoice_line(self, qty):
        """
        Prepare the dict of values to create the new invoice line for a sales order line.

        :param qty: float quantity to invoice
        """
        self.ensure_one()
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        price_unit = self.price_unit
        if self.secondary_uom_id and self.product_uom and self.product_id:
            price_unit = self.product_id.product_tmpl_id.compute_price_from_secondary_uom(
                self.secondary_uom_price_unit,
                self.secondary_uom_id,
                self.product_uom)
        elif not self.product_id and self.secondary_uom_id:
            price_unit = self.secondary_uom_price_unit
        if self.secondary_uom_id:
            res.update({'secondary_uom_price_unit': self.secondary_uom_price_unit,
                        'secondary_uom_qty': self.secondary_uom_qty,
                        'secondary_uom_id': self.secondary_uom_id.id,
                        'price_unit': price_unit,
                        })
        return res

    @api.one
    def check_secondary_uom_qty(self):
        if self.secondary_uom_id:
            product_uom_qty_theoretical = self.product_id.product_tmpl_id.convert_from_secondary_uom(
                self.secondary_uom_qty,
                self.secondary_uom_id,
                self.product_uom)
            if not tools.float_is_zero(self.product_uom_qty - product_uom_qty_theoretical,
                                       precision_rounding=self.product_uom.rounding):
                raise exceptions.ValidationError(
                    _('Nesutampa kiekiai skirtingais matavimo vienetais %s') % self.product_id.display_name)

    @api.onchange('product_id')
    def onch_prod_set_secondary_uom(self):
        if self.product_id and (
                not self.secondary_uom_id or self.secondary_uom_id not in self.product_id.product_uom_lines.mapped(
                'uom_id')):
            self.secondary_uom_id = self.product_id.uom_id

    @api.onchange('product_id', 'secondary_uom_id')
    def set_onch_list_price(self):
        if self.product_id and self.secondary_uom_id:
            line = self.product_id.product_uom_lines.filtered(lambda r: r.uom_id == self.secondary_uom_id)
            if line:
                line = line[0]
                # if not tools.float_is_zero(line.factor, precision_digits=3):
                self.secondary_uom_price_unit = self.product_id.list_price * line.factor
            elif self.product_id.uom_id == self.secondary_uom_id:
                self.secondary_uom_price_unit = self.product_id.list_price

    @api.depends('invoice_lines.invoice_id.state')
    def _compute_qty_invoiced(self):
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                if inv_line.invoice_id.state not in ['cancel']:
                    qty_inv_line_main_uom = inv_line.quantity
                    if inv_line.secondary_uom_id:
                        try:
                            qty_inv_line_main_uom = inv_line.product_id.product_tmpl_id.convert_from_secondary_uom(inv_line.secondary_uom_qty, inv_line.secondary_uom_id, inv_line.uom_id)
                        except:
                            pass
                    qty += inv_line.uom_id._compute_quantity(qty_inv_line_main_uom, line.product_uom)
            line.qty_invoiced = qty

    @api.depends('state', 'product_uom_qty', 'qty_delivered', 'qty_to_invoice', 'qty_invoiced')
    def _compute_invoice_status(self):
        super(SaleOrderLine, self)._compute_invoice_status()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if line.secondary_uom_id:
                qty_second_uom_invoiced = 0.0
                for inv_line in line.invoice_lines:
                    if inv_line.invoice_id.state != 'cancel' and inv_line.secondary_uom_id == line.secondary_uom_id:
                        qty_second_uom_invoiced += inv_line.secondary_uom_qty
                if tools.float_compare(qty_second_uom_invoiced - line.secondary_uom_qty, 0, precision_digits=precision) >=0:
                    line.invoice_status = 'invoiced'

    @api.multi
    def _get_created_move_qty(self):
        self.ensure_one()
        qty = super(SaleOrderLine, self)._get_created_move_qty()
        if self.secondary_uom_id:
            qty_secondary = 0.0
            for move in self.procurement_ids.mapped('move_ids').filtered(lambda r: r.state != 'cancel' and not r.scrapped and r.secondary_uom_id == self.secondary_uom_id):
                if move.location_dest_id.usage == "customer":
                    qty_secondary += move.secondary_uom_qty
                elif move.location_dest_id.usage == "internal" and move.to_refund_so:
                    qty_secondary -= move.secondary_uom_qty
            if tools.float_compare(qty_secondary - self.secondary_uom_qty, 0, precision_digits=2) >= 0:  # if we delivered sufficient qty in secondary uom, we delivered suffient qty in first
                qty = self.product_uom_qty
        return qty

    @api.onchange('secondary_uom_qty', 'tax_id', 'discount')
    def _onchange_discount(self):
        if not self._context.get('not_update_make_force_step'):
            self.price_subtotal_make_force_step = False

    @api.onchange('secondary_uom_price_unit')
    def _onchange_human(self):
        if self._context.get('triggered_field') == 'price_unit':
            self.price_subtotal_make_force_step = False

    @api.onchange('amount_depends')
    def onchange_amount_depends(self):
        amount = self.amount_depends
        if self._context.get('direct_trigger_amount_depends', False):
            self.price_subtotal_make_force_step = True
            self.price_subtotal_save_force_value = amount
            if self.secondary_uom_qty and not float_is_zero((1 - (self.discount or 0.0) / 100.0), precision_digits=4):
                self.secondary_uom_price_unit = (amount / self.secondary_uom_qty) / (1 - (self.discount or 0.0) / 100.0)
                for tax in self.tax_id:
                    if tax.price_include and not self.order_id.price_include:
                        self.secondary_uom_price_unit *= 1 + tax.amount / 100.0

    def _get_fields_trigger_force_price(self):
        res = super(SaleOrderLine, self)._get_fields_trigger_force_price()
        res.append('secondary_uom_qty')
        return res

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        if (isinstance(field_name, basestring) and field_name == 'secondary_uom_price_unit' or
                isinstance(field_name, list) and 'secondary_uom_price_unit' in field_name):
            self.env.context = self.with_context(triggered_field='price_unit').env.context
        return super(SaleOrderLine, self).onchange(values, field_name, field_onchange)


SaleOrderLine()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def action_confirm(self):
        self.mapped('order_line').check_secondary_uom_qty()
        return super(SaleOrder, self).action_confirm()

    @api.multi
    def _guess_so_line_by_qty(self, stock_move):
        self.ensure_one()
        all_qty_lines = self.order_line.filtered(
            lambda r: tools.float_is_zero(r.secondary_uom_qty - stock_move.secondary_uom_qty, precision_digits=2))
        lines_no_proc = all_qty_lines.filtered(lambda r: not r.procurement_ids)
        if lines_no_proc:
            return lines_no_proc[0]
        elif all_qty_lines:
            return all_qty_lines[0]
        else:
            return super(SaleOrder, self)._guess_so_line_by_qty(stock_move)


SaleOrder()
