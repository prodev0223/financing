# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from odoo import _, api, models, tools


class WriteOffReport(models.AbstractModel):
    _name = 'report.l10n_lt.report_write_off_template'

    @api.model
    def _get_default_datetime(self):
        return datetime.now()

    @api.multi
    def _get_totals(self, reconciled_lines):
        """
        Method to compute total vat, total without vat amounts and total amount written off for particular invoice;
        """
        total_write_off_no_vat = total_vat = 0
        total_write_off_invoice = {}

        invoice_move_lines = reconciled_lines.filtered(lambda l: l.invoice_id)
        payment_move_lines = reconciled_lines.filtered(lambda l: l.payment_id)
        for line in invoice_move_lines:
            invoice = line.invoice_id
            total_invoice_payments = sum((invoice.payment_move_line_ids & payment_move_lines).mapped('balance'))
            total_write_off = line.balance + total_invoice_payments
            total_write_off_invoice[invoice.id] = total_write_off
            total_vat += (total_write_off * invoice.reporting_amount_tax) / invoice.reporting_amount_total
            total_write_off_no_vat += (total_write_off * invoice.reporting_amount_untaxed) / invoice.reporting_amount_total
        return round(total_write_off_no_vat, 2), round(total_vat, 2), total_write_off_invoice

    @api.multi
    def _get_values(self, data):
        """
        Method to retrieve values used in report;
        """
        date = self._get_default_datetime()
        reconciled_lines = self.env['account.move.line'].browse(data.get('reconciled_line_ids')).exists()
        reconciled_lines -= self.env['account.move.line'].browse(data.get('write_off_line_ids')).exists()
        total_write_off_no_tax, total_vat, total_write_off_invoice = self._get_totals(reconciled_lines)

        company = self.env.user.company_id
        partner = self.env['res.partner'].browse(data.get('partner_id')).exists()

        values = {
            'date_string': _('{0}/{1}/{2}').format(date.day, date.month, date.year) or
                           self._get_default_date().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'company': company or _('Company'),
            'partner': partner or _('Partner'),
            'accountant': self.env.user or _('Accountant'),
            'invoices': reconciled_lines.mapped('invoice_id'),
            'total_write_off_no_tax': total_write_off_no_tax,
            'total_vat': total_vat,
            'total_write_off_invoice': total_write_off_invoice,
            'is_company_vat_payer': company.vat_payer,
            'is_partner_vat_payer': bool(partner.vat),
            'is_partner_a_company': partner.company_type == 'company',
            'partner_license_number': partner.license_number if hasattr(partner, 'license_number') else False,
        }
        return values

    @api.multi
    def render_html(self, doc_ids=None, data=None):
        values = self._get_values(data)
        docargs = {
            'name': data.get('name') or '-',
            'date_string': values.get('date_string'),
            'company': values.get('company'),
            'partner': values.get('partner'),
            'accountant': values.get('accountant'),
            'invoices': values.get('invoices'),
            'total_tax': values.get('total_tax'),
            'total_write_off_no_tax': values.get('total_write_off_no_tax'),
            'total_vat': values.get('total_vat'),
            'total_write_off_invoice': values.get('total_write_off_invoice'),
            'is_company_vat_payer': values.get('is_company_vat_payer'),
            'is_partner_vat_payer': values.get('is_partner_vat_payer'),
            'is_partner_a_company': values.get('is_partner_a_company'),
            'partner_license_number': values.get('partner_license_number')
        }
        return self.env['report'].render('l10n_lt.report_write_off_template', docargs)
