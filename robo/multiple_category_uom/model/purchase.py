# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    secondary_uom_id = fields.Many2one('product.uom', string='Antrinis matavimo vienetas',
                                       inverse='_set_product_qty_from_secondary')
    secondary_uom_qty = fields.Float(string='Produkto kiekis antriniais matavimo vienetais',
                                     inverse='_set_product_qty_from_secondary')
    secondary_uom_domain = fields.Many2many('product.uom', string='Leidžiami matavimo vienetai',
                                            compute='_secondary_uom_domain')
    secondary_uom_price_unit = fields.Float(string='Vieneto kaina antriniais matavimo vienetais', inverse='_set_product_qty_from_secondary')
    price_unit = fields.Float(default=1.0)
    product_qty = fields.Float(default=1.0)

    @api.one
    @api.depends('product_id')
    def _secondary_uom_domain(self):
        self.secondary_uom_domain = (self.product_id.product_uom_lines.mapped('uom_id') | self.product_id.uom_id).ids

    def compute_main_product_qty(self):
        # called regularly and from onchange
        if self.secondary_uom_id and self.product_uom and self.product_id:
            self.product_qty = self.product_id.product_tmpl_id.convert_from_secondary_uom(self.secondary_uom_qty,
                                                                                          self.secondary_uom_id,
                                                                                          self.product_uom)
        elif not self.secondary_uom_id and self.product_uom and not tools.float_is_zero(self.secondary_uom_qty,
                                                                                        precision_rounding=self.product_uom.rounding):
            self.product_qty = self.secondary_uom_qty

    def set_price_unit_from_secondary(self):
        if self.secondary_uom_id and self.product_uom and self.product_id:
            self.price_unit = self.product_id.product_tmpl_id.compute_price_from_secondary_uom(
                self.secondary_uom_price_unit,
                self.secondary_uom_id,
                self.product_uom)

    @api.one
    def _set_product_qty_from_secondary(self):
        # even if there is no
        self.compute_main_product_qty()
        self.set_price_unit_from_secondary()

    @api.onchange('secondary_uom_id', 'secondary_uom_qty')
    def onch_secondary_uom_id_qty(self):
        self.compute_main_product_qty()

    @api.onchange('secondary_uom_id', 'secondary_uom_price_unit')
    def onch_secondary_uom_id_price(self):
        self.set_price_unit_from_secondary()

    @api.one
    def check_secondary_uom_qty(self):
        if self.secondary_uom_id:
            product_uom_qty_theoretical = self.product_id.product_tmpl_id.convert_from_secondary_uom(
                self.secondary_uom_qty,
                self.secondary_uom_id,
                self.product_uom)
            rounding = self.product_uom.rounding
            diff = self.product_qty - product_uom_qty_theoretical
            if not tools.float_is_zero(diff, precision_rounding=rounding) and \
                    tools.float_compare(diff, rounding*0.5, precision_rounding=rounding/10.0) != 0:
                raise exceptions.ValidationError(
                    _('Nesutampa kiekiai pirminiais ir antriniais matavimo vienetais %s') % self.product_id.display_name)

    @api.one
    def check_secondary_uom_price(self):
        if self.secondary_uom_id:
            price_secondary = self.secondary_uom_qty * self.secondary_uom_price_unit
            price_primary = self.product_qty * self.price_unit
            if not tools.float_is_zero(price_primary - price_secondary,
                                       precision_rounding=self.order_id.currency_id.rounding):
                raise exceptions.ValidationError(_(
                    'Dėl apvalinimo neustampa kaina pagrindiniais ir antriniais matavimo vienetais. Suveskite duomenis pagrindiniais. (%s)') % self.product_id.display_name)

    @api.onchange('product_id')
    def onch_prod_set_secondary_uom(self):
        if self.product_id and (
                not self.secondary_uom_id or self.secondary_uom_id not in self.product_id.product_uom_lines.mapped(
                'uom_id')):
            self.secondary_uom_id = self.product_id.uom_id


PurchaseOrderLine()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.multi
    def button_confirm(self):
        self.mapped('order_line').check_secondary_uom_qty()
        return super(PurchaseOrder, self).button_confirm()


PurchaseOrder()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _prepare_invoice_line_from_po_line(self, line):
        res = super(AccountInvoice, self)._prepare_invoice_line_from_po_line(line)
        if line.secondary_uom_id:
            quantity = res.get('quantity', 0.0)
            if not tools.float_is_zero(line.product_qty, precision_digits=5):
                res.update({'secondary_uom_price_unit': line.secondary_uom_price_unit,
                            'secondary_uom_qty': line.secondary_uom_qty * quantity / line.product_qty,
                            'secondary_uom_id': line.secondary_uom_id.id,
                            })
        return res


AccountInvoice()
