# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.one
    def match_with_move(self, stock_move_id):
        new_procs = self.with_context(auto_set_done_procurements=True, force_procurement_create=True)._action_procurement_create()
        if new_procs:
            self.env['stock.move'].browse(stock_move_id).write({'procurement_id': new_procs[0].id})
        self.qty_delivered = self._get_delivered_qty()
        # new_procs.write({'move_dest_id': stock_move_id})

    @api.one
    def match_with_invoice_line(self, invoice_line_id):
        self.invoice_lines = [(4, invoice_line_id)]


SaleOrderLine()


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    @api.one
    def match_lines_with_pickings(self):
        unmatched_move_ids = self.picking_ids.mapped('move_lines') - self.order_line.mapped('procurement_ids.move_ids')
        for move in unmatched_move_ids:
            self.guess_so_line(move)

    @api.one
    def match_so_lines_with_inv_lines(self):
        invoices = self.invoice_ids.filtered(lambda r: r.state != 'cancel' and r.type == 'out_invoice')
        if invoices:
            unmatched_so_lines = self.order_line.filtered(lambda r: not r.invoice_lines)
            for so_line in unmatched_so_lines:
                for invoice in invoices:
                    invoice.guess_invoice_line(so_line)
            # unmatched_invoice_lines = invoices.mapped('invoice_line_ids').filtered(
            #     lambda r: not r.sale_line_ids)
            # for invoice_line in unmatched_invoice_lines:
            #     self.guess_invoice_line(invoice_line)

    @api.multi
    def _guess_so_line_by_product(self, stock_move):
        self.ensure_one()
        all_prod_lines = self.order_line.filtered(lambda r: r.product_id == stock_move.product_id)
        lines_no_proc = all_prod_lines.filtered(lambda r: not r.procurement_ids)
        if lines_no_proc:
            return lines_no_proc[0]
        elif all_prod_lines:
            return all_prod_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_by_product(self, invoice_line):
        self.ensure_one()
        all_prod_lines = self.order_line.filtered(lambda r: r.product_id == invoice_line.product_id)
        if all_prod_lines:
            return all_prod_lines[0]
        else:
            return False

    @api.multi
    def _guess_so_line_by_qty(self, stock_move):
        self.ensure_one()
        all_qty_lines = self.order_line.filtered(lambda r: tools.float_is_zero(r.product_uom_qty - stock_move.product_uom_qty, precision_digits=2))
        lines_no_proc = all_qty_lines.filtered(lambda r: not r.procurement_ids)
        if lines_no_proc:
            return lines_no_proc[0]
        elif all_qty_lines:
            return all_qty_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_by_qty(self, invoice_line):
        self.ensure_one()
        all_qty_lines = self.order_line.filtered(
            lambda r: tools.float_is_zero(r.product_uom_qty - invoice_line.quantity, precision_digits=2))
        if all_qty_lines:
            return all_qty_lines[0]
        else:
            return False

    @api.multi
    def _guess_so_line_any(self, stock_move):
        self.ensure_one()
        all_lines = self.order_line
        lines_no_proc = all_lines.filtered(lambda r: not r.procurement_ids)
        if lines_no_proc:
            return lines_no_proc[0]
        elif all_lines:
            return all_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_any(self, invoice_line):
        self.ensure_one()
        all_lines = self.order_line
        if all_lines:
            return all_lines[0]
        else:
            return False

    @api.multi
    def guess_so_line(self, stock_move):
        self.ensure_one()
        so_line = self._guess_so_line_by_product(stock_move)
        if not so_line:
            so_line = self._guess_so_line_by_qty(stock_move)
        if not so_line:
            so_line = self._guess_so_line_any(stock_move)

        if so_line:
            so_line.match_with_move(stock_move.id)

    @api.multi
    def guess_invoice_line(self, invoice_line):
        self.ensure_one()
        so_line = self._guess_invoice_line_by_product(invoice_line)
        if not so_line:
            so_line = self._guess_invoice_line_by_qty(invoice_line)
        if not so_line:
            so_line = self._guess_invoice_line_any(invoice_line)

        if so_line:
            so_line.match_with_invoice_line(invoice_line.id)

    @api.one
    def match_lines_if_necessary(self):
        if all(pick.state in ('done', 'cancel') for pick in self.picking_ids) \
                and all(inv.state in ('open', 'paid', 'cancel') for inv in self.invoice_ids):
            self.match_lines_with_pickings()
            self.match_so_lines_with_inv_lines()
        else:
            raise exceptions.UserError(
                _('Prieš užrakinant užsakymą reikia atšaukti nepatvirtintus važtaraščius ir sąskaitas'))

    @api.multi
    def action_done(self):
        res = super(SaleOrder, self).action_done()
        self.sudo().match_lines_if_necessary()
        # Force analytics on action done
        invoice_lines = self.mapped('order_line.invoice_lines')
        invoice_lines.force_picking_aml_analytics_prep()
        return res


SaleOrder()


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def _guess_invoice_line_by_product(self, so_line):
        all_prod_lines = self.mapped('invoice_line_ids').filtered(lambda r: r.product_id == so_line.product_id)
        lines_no_so = all_prod_lines.filtered(lambda r: not r.sale_line_ids)
        if lines_no_so:
            return lines_no_so[0]
        elif all_prod_lines:
            return all_prod_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_by_qty(self, so_line):
        all_qty_lines = self.mapped('invoice_line_ids').filtered(
            lambda r: tools.float_is_zero(r.quantity - so_line.product_uom_qty, precision_digits=2))
        lines_no_so = all_qty_lines.filtered(lambda r: not r.sale_line_ids)
        if lines_no_so:
            return lines_no_so[0]
        elif all_qty_lines:
            return all_qty_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_product_any(self, so_line):
        self.ensure_one()
        all_lines = self.mapped('invoice_line_ids')
        lines_no_so = all_lines.filtered(lambda r: not r.sale_line_ids and r.product_id.type == so_line.product_id.type)
        if lines_no_so:
            return lines_no_so[0]
        elif all_lines:
            return all_lines[0]
        else:
            return False

    @api.multi
    def _guess_invoice_line_any(self, so_line):
        self.ensure_one()
        all_lines = self.mapped('invoice_line_ids')
        lines_no_so = all_lines.filtered(lambda r: not r.sale_line_ids)
        if lines_no_so:
            return lines_no_so[0]
        elif all_lines:
            return all_lines[0]
        else:
            return False

    @api.multi
    def guess_invoice_line(self, so_line):
        invoice_line = self._guess_invoice_line_by_product(so_line)
        if not invoice_line:
            invoice_line = self._guess_invoice_line_by_qty(so_line)
        if not invoice_line:
            invoice_line = self._guess_invoice_line_product_any(so_line)
        if not invoice_line:
            invoice_line = self._guess_invoice_line_any(so_line)

        if invoice_line:
            so_line.match_with_invoice_line(invoice_line.id)


AccountInvoice()

