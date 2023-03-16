# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    amount_total_tax_exc_sale_origin = fields.Float(
        string='Suma be PVM (Pardavimo nurodymas)', compute='_compute_amounts_sale_origin', store=True)

    amount_total_tax_inc_sale_origin = fields.Float(
        string='Suma su PVM (Pardavimo nurodymas)', compute='_compute_amounts_sale_origin', store=True)

    @api.multi
    @api.depends('sale_line_ids.price_reduce_taxexcl', 'sale_line_ids.price_reduce_taxinc',
                 'price_unit', 'price_unit_tax_included_company', 'price_unit_tax_excluded_company')
    def _compute_amounts_sale_origin(self):
        """
        Compute amount total (price_unit * quantity) for invoice line based on price unit of the
        related sale order line. Situation: SO has product x - 10 EUR, Y - 5 EUR and invoice
        is modified as follows so it is more appealing to client:
        product x - 15 EUR, Y - 0 EUR - We want to preserve the original Y price
        :return: None
        """
        company_curr = self.env.user.sudo().company_id.currency_id
        for rec in self:
            amount_tax_inc = rec.price_unit_tax_included_company
            amount_tax_exc = rec.price_unit_tax_excluded_company
            final_price_to_force_inc = amount_tax_inc * rec.quantity
            final_price_to_force_exc = amount_tax_exc * rec.quantity
            order_id = rec.sale_line_ids.mapped('order_id')
            if order_id and len(order_id) == 1:

                corresponding_lines = rec.sale_line_ids.filtered(lambda x: x.qty_invoiced == rec.quantity)
                if not corresponding_lines:
                    corresponding_lines = rec.sale_line_ids.filtered(lambda x: x.product_qty > 0)
                if corresponding_lines:
                    # Add more sanity checks
                    if len(corresponding_lines) > 1:
                        # Filter out the lines by prices
                        corresponding_lines_filtered = corresponding_lines.filtered(
                            lambda x: not tools.float_is_zero(x.price_reduce_taxexcl, precision_digits=2) and
                            not tools.float_is_zero(x.price_reduce_taxinc, precision_digits=2)
                        )
                        # If there's no lines or if there's more than one, ensure that
                        # current invoice line is contained in all of them
                        if len(corresponding_lines_filtered) != 1:
                            lines = corresponding_lines_filtered or corresponding_lines
                            corresponding_lines_filtered = lines.filtered(
                                lambda x: rec.id in x.invoice_lines.ids
                            )
                        corresponding_lines = corresponding_lines_filtered

                    price_reduce_tax_inc = sum(x.price_reduce_taxinc for x in corresponding_lines)
                    price_reduce_tax_excl = sum(x.price_reduce_taxexcl for x in corresponding_lines)
                    ctx = self._context.copy()
                    ctx.update({'date': order_id.confirmation_date})

                    # Compute amounts based on company currency
                    sale_amount_tax_inc = order_id.pricelist_id.currency_id.with_context(ctx).compute(
                        price_reduce_tax_inc, company_curr)
                    sale_amount_tax_exc = order_id.pricelist_id.currency_id.with_context(ctx).compute(
                        price_reduce_tax_excl, company_curr)

                    price_unit_to_force_inc = amount_tax_inc
                    price_unit_to_force_exc = amount_tax_exc

                    if tools.float_compare(amount_tax_inc, sale_amount_tax_inc, precision_digits=2) != 0:
                        price_unit_to_force_inc = sale_amount_tax_inc
                    final_price_to_force_inc = price_unit_to_force_inc * rec.quantity
                    if tools.float_compare(amount_tax_exc, sale_amount_tax_exc, precision_digits=2) != 0:
                        price_unit_to_force_exc = sale_amount_tax_exc
                    final_price_to_force_exc = price_unit_to_force_exc * rec.quantity
            rec.amount_total_tax_exc_sale_origin = final_price_to_force_exc
            rec.amount_total_tax_inc_sale_origin = final_price_to_force_inc

    @api.multi
    @api.depends('amount_total_tax_exc_sale_origin', 'purchase_line_id.move_ids.state', 'invoice_id.state',
                 'sale_line_ids.procurement_ids.move_ids.state', 'product_id.type',
                 'sale_line_ids.procurement_ids.move_ids.non_error_quant_ids.cost',
                 'purchase_line_id.move_ids.non_error_quant_ids.cost',
                 'invoice_id.picking_id.move_lines.non_error_quant_ids.cost')
    def _gp(self):
        """
        ! IMPORTANT ! -- Method fully overridden in this module (original method in - robo/saskaitos/saskaitos.py)
        Calculate invoice line profit margin based on sale order line
        :return:
        """
        for line in self:
            if line.invoice_id.type in ['out_invoice', 'out_refund'] and line.invoice_id.state in ['open', 'paid']:
                # !! IMPORTANT use line sudo as separate calculations object, and non-sudo line to write to it
                line_sudo = line.sudo()
                line.no_stock_moves = False
                revenue = line.amount_total_tax_exc_sale_origin
                if line.invoice_id.type == 'out_refund':
                    revenue = -abs(revenue)
                if line.product_id.type == 'service':
                    line.gp = revenue
                    continue
                purchase_move_ids = line_sudo.mapped('purchase_line_id.move_ids').filtered(lambda r: r.state == 'done')
                sale_move_ids = line_sudo.mapped('sale_line_ids.procurement_ids.move_ids').filtered(
                    lambda r: r.state == 'done')
                if purchase_move_ids:
                    move_ids = purchase_move_ids
                elif sale_move_ids:
                    move_ids = sale_move_ids
                elif line.invoice_id.picking_id:
                    move_ids = line_sudo.invoice_id.picking_id.move_lines.filtered(lambda r: r.state == 'done')
                else:
                    line.cost = 0.0
                    line.gp = revenue
                    line.no_stock_moves = True
                    continue
                product_move_ids = move_ids
                proportion = 1.0
                if line_sudo.invoice_id.picking_id:
                    product_move_ids = move_ids.filtered(lambda r: r.product_id == line.product_id)
                    total_invoice_product_qty = sum(
                        line_sudo.invoice_id.invoice_line_ids.filtered(
                            lambda r: r.product_id == line.product_id).mapped('quantity'))
                    if total_invoice_product_qty > 0:
                        proportion = line.quantity / float(total_invoice_product_qty)

                invoice_qty_proportion = 1.0
                sale_invoice_lines = line_sudo.mapped('sale_line_ids.invoice_lines').filtered(
                    lambda r: r.invoice_id.state in ['open', 'paid'])
                if len(sale_invoice_lines) > 1:
                    total_invoice_product_qty = sum(line_sudo.mapped('sale_line_ids.invoice_lines').filtered(
                        lambda r: r.product_id == line.product_id).mapped('quantity'))
                    if total_invoice_product_qty > 0:
                        invoice_qty_proportion = line.quantity / float(total_invoice_product_qty)
                cost = sum(q.cost * q.qty for q in
                           product_move_ids.mapped('non_error_quant_ids')) * proportion * invoice_qty_proportion
                if tools.float_compare(revenue, 0.0, precision_digits=2) >= 0:
                    line.gp = revenue - cost
                    line.cost = cost
                else:
                    line.cost = -cost
                    line.gp = revenue - line.cost


AccountInvoiceLine()
