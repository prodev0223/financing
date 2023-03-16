# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, _, api, tools, exceptions
from odoo.tools import float_compare, float_is_zero


class ResCompany(models.Model):
    _inherit = 'res.company'

    auto_sale_picking_create = fields.Boolean(string='Auto sale picking create', default=True)


ResCompany()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    price_subtotal_make_force_step = fields.Boolean(string='Force step', default=False,
                                                    lt_string='Naudoti priverstinę vertę',
                                                    inverse='_inverse_amount_depends')
    price_subtotal_save_force_value = fields.Float(string='Force value', default=0.0, lt_string='Priverstinė vertė')
    amount_depends = fields.Monetary(string='Suma', readonly=False, compute='_update_amount_depends')
    require_vat = fields.Boolean(related='order_id.show_vat')
    price_unit = fields.Float()
    discount = fields.Float()
    product_uom_qty = fields.Float(required=False)

    delivery_status = fields.Selection([('delivered', 'Viskas išsiųsta'),
                                        ('to deliver', 'Reikia išsiųsti'),
                                        ('no', 'Nėra, ką išsiųsti')],
                                       string='Pristatymo būsena', lt_string='Pristatymo statusas',
                                       compute='_compute_delivery_status', store=True,
                                       readonly=True)

    # We put it here to remove the dependency on product_uom_qty which causes problem: whenever you change quantity, it
    # resets the prices. With multiple_category_uom, when you set a secondary_uom_qty value with more digits than
    # standard precision, at some point, it might be rounded back to two digits, triggering a change of product_uom_qty,
    # that would reset price_unit to list price (why is it even needed in the first place, and not only when changing
    # product_uom, I don't know..). This then triggers a change in _amount_depends, and then a recomputation of
    # secondary_uom_price_unit, with the new amount depends, which has the same consequence as resetting
    # secondary_uom_price_unit to price_unit * factor. By removing product_uom_qty from the onchange list, it does not
    # happen anymore
    @api.onchange('product_uom')
    def product_uom_change(self):
        if not self.product_uom:
            self.price_unit = 0.0
            return
        if self.order_id.pricelist_id and self.order_id.partner_id:
            product = self.product_id.with_context(
                lang=self.order_id.partner_id.lang,
                partner=self.order_id.partner_id.id,
                quantity=self.product_uom_qty,
                date_order=self.order_id.date_order,
                pricelist=self.order_id.pricelist_id.id,
                uom=self.product_uom.id,
                fiscal_position=self.env.context.get('fiscal_position')
            )
            self.price_unit = self.env['account.tax']._fix_tax_included_price(self._get_display_price(product),
                                                                              product.taxes_id, self.tax_id)

    @api.onchange('amount_depends')
    def onchange_amount_depends(self):
        amount = self.amount_depends
        if self._context.get('direct_trigger_amount_depends', False):
            self.price_subtotal_make_force_step = True
            self.price_subtotal_save_force_value = amount
            # P3:DivOK
            if self.product_uom_qty and not float_is_zero((1 - (self.discount or 0.0) / 100.0), precision_digits=4):
                self.price_unit = (amount / self.product_uom_qty) / (1 - (self.discount or 0.0) / 100.0)  # P3:DivOK
                for tax in self.tax_id:
                    if tax.price_include and not self.order_id.price_include:
                        self.price_unit *= 1 + tax.amount / 100.0  # P3:DivOK

    @api.one
    def _inverse_amount_depends(self):
        if self.price_subtotal_make_force_step:
            self.amount_depends = self.price_subtotal_save_force_value
        else:
            # P3:DivOK
            self.amount_depends = self.price_unit * self.product_qty * (1 - ((self.discount / 100.0) or 0.0))

    @api.one
    @api.depends('price_unit', 'product_uom_qty', 'discount', 'product_qty', 'product_uom',
                  'price_subtotal_make_force_step', 'price_subtotal_save_force_value')
    def _update_amount_depends(self):
        if self.price_subtotal_make_force_step:
            self.amount_depends = self.price_subtotal_save_force_value
        else:
            if self.product_id and self.product_uom:
                quantity = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id, round=False)
            else:
                quantity = self.product_qty
            self.amount_depends = self.price_unit * quantity * (1 - ((self.discount / 100.0) or 0.0))  # P3:DivOK

    @api.onchange('discount', 'tax_id', 'product_uom_qty')
    def _onchange_discount(self):
        if not self._context.get('not_update_make_force_step'):
            self.price_subtotal_make_force_step = False

    @api.onchange('product_id')
    def _onchange_product_id_reset_force_step(self):
        self.price_subtotal_make_force_step = False

    @api.onchange('price_unit')
    def _onchange_human(self):
        if self._context.get('triggered_field') == 'price_unit':
            self.price_subtotal_make_force_step = False

    @api.one
    @api.depends('price_unit', 'discount', 'tax_id', 'product_uom_qty', 'product_id',
                 'order_id.currency_id', 'order_id.company_id', 'order_id.date_order', 'order_id.partner_id',
                 'order_id.price_include_selection')
    def _compute_amount(self):
        currency = self.order_id and self.order_id.currency_id or None

        if self.price_subtotal_make_force_step:
            # P3:DivOK
            price = self.price_subtotal_save_force_value / self.product_qty if self.product_qty else 0.0
        else:
            price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)  # P3:DivOK
        inc = self.order_id.price_include_selection == 'inc'
        if self.product_uom != self.product_id.uom_id:
            # Sanitize the value so it does not contain 0.000000001 at the end
            # and it is rounded correctly afterwards.
            max_rounding = max(self.env['decimal.precision'].precision_get('Product Price'), 8)
            product_uom_qty = tools.float_round(self.product_uom_qty, precision_rounding=max_rounding)
            product_qty = self.product_uom._compute_quantity(product_uom_qty, self.product_id.uom_id)
        else:
            product_qty = self.product_uom_qty
        taxes = self.tax_id.with_context(price_include=inc).compute_all(
            price, currency, product_qty,
            product=self.product_id,
            partner=self.order_id.partner_id,
            force_total_price=self.price_subtotal_make_force_step and self.price_subtotal_save_force_value or None
        )
        self.update({
            'price_tax': taxes['total_included'] - taxes['total_excluded'] if taxes else 0.0,
            'price_total': taxes['total_included'] if taxes else self.price_subtotal_save_force_value,
            'price_subtotal': taxes['total_excluded'] if taxes else self.price_subtotal_save_force_value
            })

    @staticmethod
    def _get_fields_trigger_force_price():
        return ['discount', 'product_uom_qty', 'product_id']

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        if (isinstance(field_name, basestring) and field_name == 'price_unit' or
                isinstance(field_name, list) and 'price_unit' in field_name):
            self.env.context = self.with_context(triggered_field='price_unit').env.context
        if (isinstance(field_name, basestring) and field_name == 'amount_depends' or
                isinstance(field_name, list) and 'amount_depends' in field_name):
            self.env.context = self.with_context(direct_trigger_amount_depends=True).env.context
        else:
            self.env.context = self.with_context(direct_trigger_amount_depends=False).env.context
        fields_trigger_force_price = self._get_fields_trigger_force_price()
        if (isinstance(field_name, basestring) and field_name not in fields_trigger_force_price or
                isinstance(field_name, list) and len(field_name) == 1 and field_name not in fields_trigger_force_price):
            self.env.context = self.with_context(not_update_make_force_step=True).env.context
        return super(SaleOrderLine, self).onchange(values, field_name, field_onchange)

    @api.multi
    def _prepare_invoice_line(self, qty):
        self.ensure_one()
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        res.update({'price_subtotal_make_force_step': self.price_subtotal_make_force_step,
                    'price_subtotal_save_force_value': self.price_subtotal_save_force_value})
        return res

    @api.depends('state', 'product_qty', 'qty_delivered')
    def _compute_delivery_status(self):
        """
        Compute the delivery status of a SO line. Possible statuses:
        - no: if the SO line is not in status 'sale' or 'done', we consider that there is nothing to
          deliver. This is also the default value if the SO lines products are not deliverable
        - to deliver: there are still products to deliver
        - delivered: all products have been delivered
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if line.state not in ('sale', 'done'):
                line.delivery_status = 'no'
            elif line.product_id.type == 'product':
                if float_compare(line.qty_delivered, line.product_qty, precision_digits=precision) >= 0:
                    line.delivery_status = 'delivered'
                else:
                    line.delivery_status = 'to deliver'
            else:
                line.delivery_status = 'no'

    @api.model
    def _action_procurement_create(self):
        if self._context.get('not_create_procurements'):
            return
        else:
            return super(SaleOrderLine, self)._action_procurement_create()

    @api.multi
    def _get_created_move_qty(self):
        self.ensure_one()
        qty = 0.0
        for move in self.procurement_ids.mapped('move_ids').filtered(lambda r: r.state != 'cancel' and not r.scrapped):
            try:
                if move.location_dest_id.usage == "customer":
                    qty += move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom)
                elif move.location_dest_id.usage == "internal" and move.to_refund_so:
                    qty -= move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom)
            except:  # if someone changed uom
                pass
        return qty

    @api.multi
    def _prepare_order_line_procurement(self, group_id=False):
        self.ensure_one()
        res = super(SaleOrderLine, self)._prepare_order_line_procurement(group_id=group_id)
        if self.order_id.force_date:
            res.update({'date_planned': self.order_id.force_date + ' 10:00:00'})
        return res

    @api.one
    def _change_taxes_price_included(self):
        price_include = self.order_id.price_include
        taxes = []
        tax_obj = self.env['account.tax']
        for tax in self.tax_id:
            if tax.price_include != price_include:
                taxes.append((3, tax.id))
                if price_include and not tax.name.endswith(' su PVM'):
                    new_name = tax.name + ' su PVM'
                elif len(tax.name) > 7:
                    new_name = tax.name[:-7]
                else:
                    raise exceptions.UserError(_('Netinkamas mokesčio pavadinimas %s') % tax.name)
                tax_id = tax_obj.search([('nondeductible', '=', tax.nondeductible),
                                         ('code', '=', tax.code),
                                         ('name', '=', new_name),
                                         ('price_include', '=', price_include),
                                         ('type_tax_use', '=', tax.type_tax_use)],
                                        limit=1)
                if tax_id:
                    taxes.append((4, tax_id.id))
        if taxes:
            self.tax_id = taxes


SaleOrderLine()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    show_create_pickings = fields.Boolean(
        string='Show create pickings button',
        compute='_compute_show_create_pickings',
    )
    force_date = fields.Date(string='Force date', lt_string='Priverstinė data',
                             help='Jeigu užstatyta, naudojama tiek kuriamiems važtaraščiams, tiek sąskaitoms',
                             states={'done': [('readonly', True)]}, sequence=100,
                             )
    price_include_selection = fields.Selection([('exc', 'be PVM'), ('inc', 'su PVM')], string='Kainos',
                                               lt_string='Kainos', default='exc', inverse='inverse_price_selection')
    price_include = fields.Boolean(string='Kainos su PVM', compute='_price_include')

    show_vat = fields.Boolean(compute='_show_vat')

    delivery_status = fields.Selection([
        ('delivered', 'Viskas išsiųsta'),
        ('to deliver', 'Reikia išsiųsti'),
        ('no', 'Nėra, ką išsiųsti'),
    ], string='Pristatymo būsena', compute='_get_delivered', store=True, readonly=True)

    @api.one
    @api.depends('name', 'company_id', 'date_order')
    def _show_vat(self):
        self.show_vat = self.company_id.sudo().with_context({'date': self.date_order}).vat_payer

    @api.onchange('show_vat')
    def set_reset_tax_line_ids(self):
        for line in self.order_line:
            line._compute_tax_id()

    @api.depends('order_line.price_total')
    def _amount_all(self):
        company_currency = self.sudo().env.user.company_id.currency_id
        for order in self:
            currency = order.pricelist_id.currency_id or company_currency
            amount_untaxed = amount_tax = amount_total = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                amount_total += line.price_total
                if order.company_id.tax_calculation_rounding_method == 'round_globally':
                    if line.price_subtotal_make_force_step:
                        if line.product_uom_qty:
                            price = line.price_subtotal_save_force_value / line.product_uom_qty  # P3:DivOK
                        else:
                            price = 0.0
                    else:
                        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)  # P3:DivOK
                    inc = order.price_include_selection == 'inc'
                    taxes = line.tax_id.with_context(price_include=inc).compute_all(
                        price, order.currency_id, line.product_uom_qty,
                        product=line.product_id,
                        partner=order.partner_id,
                        force_total_price=line.price_subtotal_make_force_step and line.price_subtotal_save_force_value or None
                    )
                    if taxes:
                        amount_tax += sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                else:
                    amount_tax += line.price_tax
            if order.price_include:
                order.update({
                    'amount_untaxed': currency.round(amount_total - amount_tax),
                    'amount_tax': currency.round(amount_tax),
                    'amount_total': currency.round(amount_total)
                })
            else:
                order.update({
                    'amount_untaxed': currency.round(amount_untaxed),
                    'amount_tax': currency.round(amount_tax),
                    'amount_total': currency.round(amount_untaxed) + currency.round(amount_tax),
                })

    @api.one
    @api.depends('price_include_selection')
    def _price_include(self):
        self.price_include = self.price_include_selection == 'inc'

    @api.onchange('price_include_selection')
    def onchange_price_include(self):
        self.change_taxes_price_included()

    @api.multi
    def inverse_price_selection(self):
        for rec in self:
            rec.change_taxes_price_included()

    @api.multi
    def change_taxes_price_included(self):
        self.ensure_one()
        for line in self.order_line:
            line._change_taxes_price_included()

    @api.depends('state', 'order_line.delivery_status')
    def _get_delivered(self):
        """
        Compute the delivery status of a SO. Possible statuses:
        - no: if the SO is not in status 'sale' or 'done', we consider that there is nothing to
          deliver. If no SO lines is in 'to deliver' or 'delivered', also no.
        - to deliver: if any SO line is 'to deliver', the whole SO is 'to deliver'
        - delivered: if no "non 'no'" SO lines are left in 'to deliver', SO is 'delivered'
        """
        for order in self:
            order.delivery_status = 'no'
            lines = order.order_line.filtered(lambda l: l.delivery_status != 'no')
            if lines:
                if any([line.delivery_status == 'to deliver' for line in lines]):
                    order.delivery_status = 'to deliver'
                else:
                    order.delivery_status = 'delivered'

    @api.multi
    @api.depends('state')
    def _compute_show_create_pickings(self):
        """Checks whether create picking button should be shown on order"""
        # Ignore auto_sale_picking_create in this case, because it should only be used
        # on automatic actions, and in this case, we want users to allow manual creation
        # if not all lines from SO are present in the picking
        for rec in self.filtered(lambda x: x.state == 'sale'):
            show_create_pickings = False
            for line in rec.order_line:
                qty_move_created = line._get_created_move_qty()
                if tools.float_compare(line.product_uom_qty, qty_move_created, precision_digits=2) > 0:
                    show_create_pickings = True
                    break
            rec.show_create_pickings = show_create_pickings

    @api.multi
    def action_confirm(self):
        for order in self:
            price_incl = order.price_include
            if any([tax.price_include != price_incl for tax in order.mapped('order_line.tax_id')]):
                raise exceptions.UserError(_('Neteisingai nurodyti mokesčiai. Pabandykite pakeisti kainų skaičivimą su PVM arba be PVM. Jei nepavyks - kreipkitės į buhalterį.'))
        if not self.env.user.company_id.auto_sale_picking_create:
            return super(SaleOrder, self.with_context(not_create_procurements=True)).action_confirm()
        else:
            return super(SaleOrder, self).action_confirm()

    @api.multi
    def action_invoice_create(self, grouped=False, final=False):
        for order in self:
            price_incl = order.price_include
            if any([tax.price_include != price_incl for tax in order.mapped('order_line.tax_id')]):
                raise exceptions.UserError(_('Neteisingai nurodyti mokesčiai. Kreipkitės į buhalterį.'))
        return super(SaleOrder, self).action_invoice_create(grouped=grouped, final=final)

    @api.multi
    def create_pickings(self):
        for rec in self:
            for line in rec.order_line:
                line._action_procurement_create()

    @api.model
    def create(self, vals):
        if not self.env.user.company_id.auto_sale_picking_create:
            return super(SaleOrder, self.with_context(not_create_procurements=True)).create(vals)
        else:
            return super(SaleOrder, self).create(vals)

    @api.multi
    def write(self, vals):
        if not self.env.user.company_id.auto_sale_picking_create:
            return super(SaleOrder, self.with_context(not_create_procurements=True)).write(vals)
        else:
            return super(SaleOrder, self).write(vals)

    @api.multi
    def action_cancel_invoices(self):
        invoices = self.mapped('invoice_ids')
        if any([inv.state == 'paid' for inv in invoices]):
            raise exceptions.UserError(
                _('Kai kurios sąskaitos jau apmokėtos, pirmiausia atšaukite sąskaitas.'))
        for inv in invoices:
            if inv.state not in ['paid', 'cancel']:
                inv.action_invoice_cancel()
            if inv.state == 'cancel' and not inv.move_name:
                inv.unlink()

    @api.multi
    def action_cancel_deliveries(self):
        pickings = self.mapped('picking_ids').filtered(lambda pick: pick.location_id.usage == 'internal' and
                                                          pick.location_dest_id.usage == 'customer' and
                                                          any([move.non_error_quant_ids for move in pick.move_lines]))
        for picking in pickings:
            for move in picking.move_lines:
                if any([q.location_id != picking.location_dest_id for q in move.quant_ids]):
                    raise exceptions.UserError(
                        _('Važtaraščiai negali būti atšaukti.'))
        for picking in pickings:
            picking_return = self.env['stock.return.picking'].with_context(active_id=picking.id).create(
                {'mistake_type': 'cancel', 'error': True})
            picking_return._create_returns()

    @api.multi
    def action_delete_deliveries(self):
        try:
            self.mapped('picking_ids').filtered(lambda pick: pick.state == 'cancel').unlink()
        except:
            pass

    @api.multi
    def action_cancel(self):
        self.action_cancel_invoices()
        self.action_cancel_deliveries()
        res = super(SaleOrder, self).action_cancel()
        self.action_delete_deliveries()
        return res

    @api.multi
    def _prepare_invoice(self):
        self.ensure_one()
        res = super(SaleOrder, self)._prepare_invoice()
        if self.force_date:
            res.update({'date_invoice': self.force_date})
        res.update({'price_include_selection': self.price_include_selection})
        return res


SaleOrder()
