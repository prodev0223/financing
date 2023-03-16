# -*- coding: utf-8 -*-

from odoo import api, models


class CashReceiptReport(models.AbstractModel):
    _name = 'report.sl_general_report.report_cash_receipt_template'

    def get_lines(self, journal_id, payment_type):
        journal = self.env['account.journal'].browse(journal_id).exists()
        if not journal:
            return dict()
        domain = [('journal_id', '=', journal_id)]
        if payment_type and payment_type != 'all':
            domain.append(('payment_type', '=', payment_type))
        receipts = self.env['cash.receipt'].search(domain).sorted(key=lambda r: r.payment_date, reverse=True)
        lines = []
        for receipt in receipts:
            line = {
                'receipt_no': receipt.name,
                'date': receipt.payment_date,
                'payment_type_name': unicode(dict(receipt._fields['payment_type'].selection).get(receipt.payment_type)),
                'payment_type': receipt.payment_type,
                'amount': receipt.amount,
                'balance': -receipt.amount if receipt.payment_type == 'outbound' else receipt.amount,
                'partner': receipt.partner_id.name,
                'cashier': receipt.cashier_id.name,
            }
            lines.append(line)
        return lines

    @api.multi
    def render_html(self, doc_ids=None, data=None):
        company = self.env.user.company_id
        date_from = data['form']['date_from']
        date_to = data['form']['date_to']
        journal_id = data['form']['journal_id'][0]
        payment_type = data['form']['payment_type_filter']
        lines = self.get_lines(journal_id, payment_type)

        docargs = {
            'company': company,
            'date_from': date_from,
            'date_to': date_to,
            'lines': lines,
        }
        return self.env['report'].render('sl_general_report.report_cash_receipt_template', docargs)
