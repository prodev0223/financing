# -*- coding: utf-8 -*-
from odoo import models, fields, _, api


# class AccountInvoiceLine(models.Model):
#     _inherit = 'account.invoice.line'
#
#     name = fields.Text(inverse='_recompute_picking_note')
#
#     @api.multi
#     def _recompute_picking_note(self):
#         pickings = self.sudo().mapped('invoice_id.sale_ids.picking_ids')
#         pickings.compute_note_from_invoices()
#
#
# AccountInvoiceLine()
#
#
# class StockPicking(models.Model):
#     _inherit = 'stock.picking'
#
#     @api.one
#     def compute_note_from_invoices(self):
#         invoice_lines = self.mapped('move_lines.procurement_id.sale_line_id.order_id.invoice_ids.invoice_line_ids')
#         new_note = '\n'.join(invoice_lines.mapped('name'))
#         self.sudo().write({'note': new_note})
#
#
# StockPicking()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.one
    def _compute_partner_ref(self):
        for supplier_info in self.seller_ids:
            if supplier_info.name.id == self._context.get('partner_id'):
                product_name = supplier_info.product_name or self.default_code
                break
        else:
            product_name = self.name
        self.partner_ref = product_name


ProductProduct()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def product_id_change(self):
        res = super(SaleOrderLine, self).product_id_change()
        if self.product_id and self.name and self.product_id.default_code and self.product_id.default_code in self.name:
            n = len('[' + self.product_id.default_code + ']')
            self.name = self.name[n:].strip()
        return res


SaleOrderLine()


class ReportAgedPartnerBalance(models.AbstractModel):

    _inherit = 'report.sl_general_report.report_agedpartnerbalance_sl'

    @staticmethod
    def _get_account_code_mapping():
        return {'payable': ['4430'],
                'receivable': ['2410', '2414']}


ReportAgedPartnerBalance()
