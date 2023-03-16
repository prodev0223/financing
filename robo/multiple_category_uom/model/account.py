# -*- encoding: utf-8 -*-

from odoo import models, fields, _, api, exceptions, tools
import odoo.addons.decimal_precision as dp


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    secondary_uom_id = fields.Many2one('product.uom', string='Antrinis matavimo vienetas',
                                       inverse='_set_product_qty_from_secondary')
    secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais',
                                     inverse='_set_product_qty_from_secondary')
    print_secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais',
                                           compute='_compute_print_secondary_fields')
    secondary_uom_domain = fields.Many2many('product.uom', string='Leidžiami matavimo vienetai',
                                            compute='_secondary_uom_domain')
    secondary_uom_price_unit = fields.Float(string='Vieneto kaina antriniais matavimo vienetais',
                                            inverse='_set_product_qty_from_secondary',
                                            # digits=dp.get_precision('Product Price')
                                            )
    secondary_uom_price_unit_tax_excluded = fields.Float(
        string='Vieneto kaina antriniais matavimo vienetais be mokesčių',
        compute='_secondary_uom_price_unit_tax_excluded'
    )
    price_unit = fields.Float(default=0.0)
    quantity = fields.Float(compute='_set_qty_from_secondary_uom_id_qty', default=0.0, store=True)
    amount_depends = fields.Monetary(string='Suma', compute='_amount_depends', readonly=False)
    price_subtotal = fields.Monetary(compute='_compute_price')
    price_subtotal_signed = fields.Monetary(compute='_compute_price')

    @api.one
    @api.depends('invoice_id.type')
    def _compute_print_secondary_fields(self):
        sign = -1.0 if 'refund' in self.invoice_id.type else 1.0
        self.print_secondary_uom_qty = sign * self.secondary_uom_qty

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
                 'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id')
    def _compute_price(self):
        currency = self.invoice_id and self.invoice_id.currency_id or None
        if self.secondary_uom_id and self.uom_id and self.product_id:
            quantity = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                  self.secondary_uom_id,
                                                                                  self.uom_id)
        elif (not self.secondary_uom_id and self.uom_id and
              not tools.float_is_zero(self.secondary_uom_qty, precision_rounding=self.uom_id.rounding)) \
                or not self.product_id and self.secondary_uom_id:
            quantity = self.secondary_uom_qty
        else:
            quantity = self.quantity
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = False
        if self.invoice_line_tax_ids:
            taxes = self.invoice_line_tax_ids.compute_all(price, currency, quantity, product=self.product_id,
                                                          partner=self.invoice_id.partner_id)
        self.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else quantity * price
        if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
            use_rounding = currency.apply_currency_rounding(price_subtotal_signed)
            price_subtotal_signed = self.invoice_id.currency_id.compute(
                price_subtotal_signed, self.invoice_id.company_id.currency_id, round=use_rounding)
        sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
        self.price_subtotal_signed = price_subtotal_signed * sign

    @api.one
    @api.depends('invoice_id.price_include_selection', 'price_subtotal', 'price_unit', 'quantity',
                 'price_subtotal_make_force_step', 'price_subtotal_save_force_value', 'discount')
    def _amount_depends(self):
        if self.price_subtotal_make_force_step:
            self.amount_depends = self.price_subtotal_save_force_value
        else:
            if self.secondary_uom_id and self.uom_id and self.product_id:
                quantity = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                      self.secondary_uom_id,
                                                                                      self.uom_id)
            elif (not self.secondary_uom_id and self.uom_id and
                  not tools.float_is_zero(self.secondary_uom_qty, precision_rounding=self.uom_id.rounding)) \
                    or not self.product_id and self.secondary_uom_id:
                quantity = self.secondary_uom_qty
            else:
                quantity = self.quantity
            amount_depends = self.price_unit * quantity * (1 - ((self.discount / 100.0) or 0.0))
            self.amount_depends = tools.float_round(amount_depends, precision_digits=2)

    @api.one
    def _secondary_uom_price_unit_tax_excluded(self):
        if not tools.float_is_zero(self.secondary_uom_qty, precision_digits=2):
            self.secondary_uom_price_unit_tax_excluded = self.price_subtotal / self.secondary_uom_qty
        else:
            self.secondary_uom_price_unit_tax_excluded = self.price_unit_tax_excluded

    @api.one
    @api.depends('product_id')
    def _secondary_uom_domain(self):
        self.secondary_uom_domain = (self.product_id.sudo().product_uom_lines.mapped('uom_id') | self.product_id.uom_id).ids

    def compute_main_product_qty(self):
        # called regularly and from onchange
        if self.secondary_uom_id and self.uom_id and self.product_id:
            self.quantity = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                       self.secondary_uom_id,
                                                                                       self.uom_id)
        elif (not self.secondary_uom_id and self.uom_id and
              not tools.float_is_zero(self.secondary_uom_qty, precision_rounding=self.uom_id.rounding))\
                or not self.product_id and self.secondary_uom_id:
            self.quantity = self.secondary_uom_qty

    def set_price_unit_from_secondary(self):
        if self.price_subtotal_make_force_step:
            self.price_unit = self.price_subtotal_save_force_value / self.quantity if self.quantity else 0.0
        elif self.secondary_uom_id and self.uom_id and self.product_id:
            self.price_unit = self.product_id.product_tmpl_id.compute_price_from_secondary_uom(
                self.secondary_uom_price_unit,
                self.secondary_uom_id,
                self.uom_id)
        elif not self.product_id and self.secondary_uom_id:
            self.price_unit = self.secondary_uom_price_unit

    @api.one
    def _set_product_qty_from_secondary(self):
        # even if there is no
        # if self._context.get('force_secondary_uom'):
        #     return
        self.compute_main_product_qty()
        self.set_price_unit_from_secondary()

    @api.one
    @api.depends('secondary_uom_id', 'secondary_uom_qty', 'invoice_id.partner_id') #invoice_id.partner_id is required here to prevent quantity to be reset to default value when changing partner_id on lines that are not saved
    def _set_qty_from_secondary_uom_id_qty(self):
        # copy of compute_main_product_qty method
        if self.secondary_uom_id and self.uom_id and self.product_id:
            self.quantity = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                       self.secondary_uom_id,
                                                                                       self.uom_id)
        elif (not self.secondary_uom_id and self.uom_id and
              not tools.float_is_zero(self.secondary_uom_qty, precision_rounding=self.uom_id.rounding))\
                or not self.product_id and self.secondary_uom_id:
            self.quantity = self.secondary_uom_qty

    @api.onchange('secondary_uom_id', 'secondary_uom_price_unit')
    def onch_secondary_uom_id_price(self):
        self.set_price_unit_from_secondary()

    @api.one
    def check_secondary_uom_qty(self):
        if self.product_id and self.secondary_uom_id:
            product_uom_qty_theoretical = self.product_id.product_tmpl_id.convert_from_secondary_uom(
                self.secondary_uom_qty,
                self.secondary_uom_id,
                self.uom_id)
            if not tools.float_is_zero(self.quantity - product_uom_qty_theoretical,
                                       precision_rounding=self.uom_id.rounding):
                raise exceptions.ValidationError(
                    _('Nesutampa kiekiai skirtingais matavimo vienetais %s') % self.product_id.display_name)

    @api.one
    def check_secondary_uom_price(self):
        if self.secondary_uom_id:
            secondary_price = self.secondary_uom_qty * self.secondary_uom_price_unit * (1-self.discount/100)
            if not self.invoice_id.price_include:
                primary_price = self.price_subtotal
            else:
                primary_price = self.total_with_tax_amount
            diff = abs(secondary_price - primary_price)
            if tools.float_compare(diff, 0.02, precision_rounding=self.invoice_id.currency_id.rounding) >= 0:
                if self.invoice_id.type in ['out_invoice', 'out_refund']:
                    raise exceptions.ValidationError(
                        _('Nesutampa sumos pirminiais ir antriniais amatavimo vienetais. Įveskite sumą rankomis. (%s)')
                        % self.product_id.display_name)
                else:
                    raise exceptions.ValidationError(
                        _('Nesutampa sumos pagrindiniais ir antriniais amatavimo vienetais. Įveskite duomenis pagrindiniais matavimo vienetais. (%s)')
                        % self.product_id.display_name)

    @api.onchange('product_id')
    def onch_prod_set_secondary_uom(self):
        if self.product_id and (
                not self.secondary_uom_id or self.secondary_uom_id not in self.product_id.product_uom_lines.mapped(
                'uom_id')):
            self.secondary_uom_id = self.product_id.uom_id

    # @api.one
    # def force_secondary_uom(self):
    #     if self.secondary_uom_id and not tools.float_is_zero(self.secondary_uom_qty, precision_digits=3):
    #         if not self.invoice_id.price_include:
    #             price = self.price_subtotal
    #         else:
    #             price = self.total_with_tax_amount
    #         # This next line does not account for discounts and might cause problems
    #         self.with_context(force_secondary_uom=True).secondary_uom_price_unit = price/self.secondary_uom_qty

    @api.multi
    def write(self, vals):
        if 'product_id' in vals and self.mapped('product_id.id') != [vals['product_id']] and (
                self.mapped('secondary_uom_id') or vals.get('secondary_uom_id')):
            trigger_secondary_uom_recompute = True
        else:
            trigger_secondary_uom_recompute = False
        res = super(AccountInvoiceLine, self).write(vals)
        if trigger_secondary_uom_recompute:
            self._set_product_qty_from_secondary()
        return res

    @api.onchange('discount', 'invoice_line_tax_ids', 'secondary_uom_qty')
    def _onchange_discount(self):
        if not self._context.get('not_update_make_force_step'):
            self.price_subtotal_make_force_step = False

    @api.onchange('secondary_uom_price_unit')
    def _onchange_human(self):
        if self._context.get('triggered_field') == 'price_unit':
            self.price_subtotal_make_force_step = False

    def _get_fields_trigger_force_price(self):
        res = super(AccountInvoiceLine, self)._get_fields_trigger_force_price()
        res.append('secondary_uom_qty')
        return res

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        if isinstance(field_name, basestring) and field_name == 'secondary_uom_price_unit' or isinstance(field_name,
                                                                                           list) and 'secondary_uom_price_unit' in field_name:
            self = self.with_context(triggered_field='price_unit')
        return super(AccountInvoiceLine, self).onchange(values, field_name, field_onchange)

    @api.onchange('amount_depends')
    def onchange_amount_depends_multiple(self):
        amount = self.amount_depends
        if self._context.get('direct_trigger_amount_depends', False):
            if self.secondary_uom_qty and not tools.float_is_zero((1 - (self.discount or 0.0) / 100.0), precision_digits=4):
                self.secondary_uom_price_unit = (amount / self.secondary_uom_qty) / (
                        1 - (self.discount or 0.0) / 100.0)


AccountInvoiceLine()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def invoice_validate(self):
        # This seems to be here to ensure the unit price matches the quantity and line subtotal. This is already done by
        # other methods such as onchange_amount_depend_multiple. We are removing this part for now and will see if any problem arise
        # The next check should account for problems there and raise error in case the onchange failed
        # for inv in self:
        #     for inv_line in inv.invoice_line_ids:
        #         inv_line.force_secondary_uom()
        self.mapped('invoice_line_ids').check_secondary_uom_price()
        return super(AccountInvoice, self).invoice_validate()

    @api.multi
    def _guess_invoice_line_by_qty(self, so_line):
        all_qty_lines = self.mapped('invoice_line_ids').filtered(
            lambda r: tools.float_is_zero(r.secondary_uom_qty - so_line.secondary_uom_qty, precision_digits=2))
        lines_no_so = all_qty_lines.filtered(lambda r: not r.sale_line_ids)
        if lines_no_so:
            return lines_no_so[0]
        elif all_qty_lines:
            return all_qty_lines[0]
        else:
            return super(AccountInvoice, self)._guess_invoice_line_by_qty(so_line)


AccountInvoice()
