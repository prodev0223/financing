# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta

class AccVoucherExt(models.Model):

    _inherit = 'account.voucher.line'

    price_subtotal_signed = fields.Monetary(string='Amount Signed',
                                            store=True, readonly=True, compute='_compute_subtotal_signed')

    @api.one
    @api.depends('price_subtotal', 'voucher_id.state', 'currency_id')
    def _compute_subtotal_signed(self):
        voucher = self.voucher_id
        amount = voucher.currency_id.with_context({'date': voucher.date}).compute(self.price_subtotal, voucher.company_id.currency_id)
        self.price_subtotal_signed = amount


AccVoucherExt()


# class AccountInvoice(models.Model):
#
#     _inherit = 'account.invoice'
#
#     @api.multi
#     def action_invoice_open(self):
#         for rec in self.filtered(lambda inv: inv.type in ['in_invoice', 'in_refund']):
#             current_date = datetime.utcnow().date()
#             date_invoice_dt = datetime.strptime(rec.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
#             delta_months = relativedelta(current_date, date_invoice_dt).months
#             if delta_months > 0 and current_date.day < 16:
#                 record = self.sudo().env['vmi.document.export'].search([
#                     ('document_date', '>=',
#                      (datetime.utcnow() - relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
#                     ('document_date', '<',
#                      (datetime.utcnow() - relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT))])
#                 if record:
#                     rec.date_invoice = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
#         return super(AccountInvoice, self).action_invoice_open()
#
#
# AccountInvoice()
