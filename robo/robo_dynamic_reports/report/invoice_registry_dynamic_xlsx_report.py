# -*- coding: utf-8 -*-
from six import iteritems

from odoo import _

try:
    from odoo.report.report_sxw import rml_parse
except ImportError:
    rml_parse = None

from odoo.addons.account_dynamic_reports.report.dynamic_xlsx_report import DynamicXLSXReport


class InvoiceRegistryDynamicXLSXReport(DynamicXLSXReport):
    def generate_xlsx_report(self, workbook, data, record):
        super(InvoiceRegistryDynamicXLSXReport, self).generate_xlsx_report(workbook, data, record)

        currencies = data.get('currencies', {})
        company_currency_key = data.get('company_currency_key', {})
        vat_amounts = data.get('vat_amounts', {})
        tax_accounts = data.get('tax_accounts', {})

        if currencies:
            self.render_currency_data(currencies)

        if vat_amounts:
            self.render_vat_amounts(vat_amounts, company_currency_key)

        if tax_accounts:
            self.render_tax_accounts(tax_accounts, company_currency_key)

    def render_currency_data(self, currencies):
        self.row_pos += 1

        # Write currency table column title
        cell_format = self._get_desired_cell_format(column=0, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 0, _('Currency'), cell_format)
        cell_format = self._get_desired_cell_format(column=1, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 1, _('VAT amount'), cell_format)
        cell_format = self._get_desired_cell_format(column=2, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 2, _('Amount excl. VAT'), cell_format)
        self.row_pos += 1

        for currency_key, currency_data in iteritems(currencies):
            # Write currency data
            vat_amount = currency_data.get('pvm_suma')
            amount = currency_data.get('suma')
            if not isinstance(vat_amount, (int, float, long)) or not isinstance(amount, (int, float, long)):
                continue
            cell_format = self._get_desired_cell_format(column=0, is_header=False, is_number=False, is_totals=False)
            self.data_sheet.write_string(self.row_pos, 0, currency_key, cell_format)
            cell_format = self._get_desired_cell_format(column=1, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 1, vat_amount, cell_format)
            cell_format = self._get_desired_cell_format(column=2, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 2, amount, cell_format)
            self.row_pos += 1

    def render_vat_amounts(self, vat_amounts, company_currency_key):
        self.row_pos += 1

        # Write vat table header
        cell_format = self._get_desired_cell_format(column=0, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 0, _('VAT code'), cell_format)
        cell_format = self._get_desired_cell_format(column=1, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 1, '{}, {}'.format(_('Amount excl. VAT'), company_currency_key),
                                     cell_format)
        cell_format = self._get_desired_cell_format(column=2, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 2, '{}, {}'.format(_('VAT amount'), company_currency_key),
                                     cell_format)
        self.row_pos += 1

        for vat_code, vat_code_data in iteritems(vat_amounts):
            # Write vat data
            vat_amount = vat_code_data.get('pvm_suma')
            amount = vat_code_data.get('suma')
            if not isinstance(vat_amount, (int, float, long)) or not isinstance(amount, (int, float, long)):
                continue
            cell_format = self._get_desired_cell_format(column=0, is_header=False, is_number=False, is_totals=False)
            self.data_sheet.write_string(self.row_pos, 0, vat_code, cell_format)
            cell_format = self._get_desired_cell_format(column=1, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 1, amount, cell_format)
            cell_format = self._get_desired_cell_format(column=2, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 2, vat_amount, cell_format)
            self.row_pos += 1

    def render_tax_accounts(self, tax_accounts, company_currency_key):
        self.row_pos += 1

        # Write vat table header
        cell_format = self._get_desired_cell_format(column=0, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 0, _('Tax account'), cell_format)
        cell_format = self._get_desired_cell_format(column=1, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 1, '{}, {}'.format(_('Amount excl. VAT'), company_currency_key),
                                     cell_format)
        cell_format = self._get_desired_cell_format(column=2, is_header=True, is_number=False, is_totals=False)
        self.data_sheet.write_string(self.row_pos, 2, '{}, {}'.format(_('VAT amount'), company_currency_key),
                                     cell_format)
        self.row_pos += 1

        for tax_account, vat_code_data in iteritems(tax_accounts):
            # Write vat data
            vat_amount = vat_code_data.get('pvm_suma')
            amount = vat_code_data.get('suma')
            if not isinstance(vat_amount, (int, float, long)) or not isinstance(amount, (int, float, long)):
                continue
            cell_format = self._get_desired_cell_format(column=0, is_header=False, is_number=False, is_totals=False)
            self.data_sheet.write_string(self.row_pos, 0, tax_account, cell_format)
            cell_format = self._get_desired_cell_format(column=1, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 1, amount, cell_format)
            cell_format = self._get_desired_cell_format(column=2, is_header=False, is_number=True, is_totals=False)
            self.data_sheet.write_number(self.row_pos, 2, vat_amount, cell_format)
            self.row_pos += 1


InvoiceRegistryDynamicXLSXReport('report.robo_dynamic_reports.invoice_registry_xlsx_report', 'res.company')
