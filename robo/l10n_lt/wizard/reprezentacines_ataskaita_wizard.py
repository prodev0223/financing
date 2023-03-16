# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import xlrd
import os
from xlutils.filter import process, XLRDReader, XLWTWriter
from xlwt import Formula
from sys import platform
from odoo.tools import float_round


def copy2(wb):
    w = XLWTWriter()
    process(XLRDReader(wb,'unknown.xls'), w)
    return w.output[0][1], w.style_list


def _getOutCell(outSheet, colIndex, rowIndex):
    """ HACK: Extract the internal xlwt cell representation. """
    row = outSheet._Worksheet__rows.get(rowIndex)
    if not row: return None

    cell = row._Row__cells.get(colIndex)
    return cell


def setOutCell(outSheet, col, row, value):
    """ Change cell value without changing formatting. """
    # HACK to retain cell style.
    previousCell = _getOutCell(outSheet, col, row)
    # END HACK, PART I

    outSheet.write(row, col, value)

    # HACK, PART II
    if previousCell:
        newCell = _getOutCell(outSheet, col, row)
        if newCell:
            newCell.xf_idx = previousCell.xf_idx


def get_style(inSheet, outStyle, i, j):
    xf_index = inSheet.cell_xf_index(i, j)
    return outStyle[xf_index]

template_table_coordinates = [0, 1, 3, 5, 6, 7, 8, 9, 10, 11]


class ReprezentacinesAtaskaitaWizard(models.TransientModel):

    _name = 'reprezentacines.ataskaita.wizard'

    def _date_from(self):
        return (datetime.utcnow() - relativedelta(day=1, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _date_to(self):
        return (datetime.utcnow() - relativedelta(day=31, months=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _account_75_1(self):
        return self.env['account.account'].search([('code', '=', '63141')], limit=1)

    def _account_25_1(self):
        return self.env['account.account'].search([('code', '=', '63142')], limit=1)

    def _account_75_2(self):
        return self.env['account.account']

    def _account_25_2(self):
        return self.env['account.account']

    date_from = fields.Date(string='Date from', default=_date_from, required=True)
    date_to = fields.Date(string='Date to', default=_date_to, required=True)
    account_75_1 = fields.Many2one('account.account', string='75%', default=_account_75_1)
    account_25_1 = fields.Many2one('account.account', string='25%', default=_account_25_1)
    account_75_2 = fields.Many2one('account.account', string='75%', default=_account_75_2)
    account_25_2 = fields.Many2one('account.account', string='25%', default=_account_25_2)

    def form_first_part_xls(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\representation\\Reprezentaciju nurasymo aktas 1.xls'
        else:
            xls_flocation = '/static/src/representation/Reprezentaciju nurasymo aktas 1.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation

        if platform == 'win32':
            wrt_loc = '\\static\\src\\representation\\tmp.xls'
        else:
            wrt_loc = '/static/src/representation/tmp.xls'
        wrt_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + wrt_loc

        # wrt_loc = create_temporary_copy(file_loc)
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)
        sheet = wb.get_sheet(0)
        company = self.env.user.company_id
        setOutCell(sheet, 0, 0, company.name)
        setOutCell(sheet, 0, 2, 'Im. k. ' + (company.company_registry or ''))
        setOutCell(sheet, 10, 8, company.vadovas.name)

        return rb, wrt_loc, wb, wstyle

    @api.multi
    def generate(self):
        account_pairs = [(self.account_75_1.id, self.account_25_1.id), (self.account_75_2.id, self.account_25_2.id)]
        file_1 = ''
        file_2 = ''
        currency = self.env.user.company_id.currency_id
        for file_num, (acc_75_id, acc_25_id) in enumerate(account_pairs):
            in_xls, xls_location, write_xls, wstyle = self.form_first_part_xls()
            in_sheet = in_xls.sheet_by_index(0)
            wsheet = write_xls.get_sheet(0)
            account_invoices = self.env['account.invoice.line'].search([('account_id', 'in', [acc_75_id, acc_25_id]),
                                                                        ('invoice_id.state', 'in', ['open', 'paid']),
                                                                        ('invoice_id.date_invoice', '>=', self.date_from),
                                                                        ('invoice_id.date_invoice', '<=', self.date_to)]).\
                mapped('invoice_id').sorted(lambda r: r.date)

            num_acc_inv = len(account_invoices)
            for i, invoice in enumerate(account_invoices):
                wsheet.merge(26+i, 26+i, 1, 2)
                wsheet.merge(26+i, 26+i, 3, 4)
                for j in template_table_coordinates and range(12):
                    wsheet.write(26 + i, j, '', get_style(in_sheet, wstyle, 26, j))
                amount_75 = sum(invoice.invoice_line_ids.filtered(lambda r: r.account_id.id == acc_75_id).mapped(
                    'price_subtotal_signed'))
                amount_25 = sum(invoice.invoice_line_ids.filtered(lambda r: r.account_id.id == acc_25_id).mapped(
                    'price_subtotal_signed'))
                total_without_tax = amount_75 + amount_25
                # tax_amount_curr = sum(
                #     invoice.invoice_line_ids.filtered(lambda r: r.account_id.id in (acc_75_id, acc_25_id)).mapped(
                #         'tax_amount'))
                # tax_amount = invoice.currency_id.with_context(date=invoice.date_invoice).compute(tax_amount_curr,
                #                                                                                  currency)
                total_with_tax_cur = sum(
                    invoice.invoice_line_ids.filtered(lambda r: r.account_id.id in (acc_75_id, acc_25_id)).mapped(
                        'total_with_tax_amount'))
                total_with_tax = invoice.currency_id.with_context(date=invoice.date_invoice).compute(total_with_tax_cur,
                                                                                                     currency)
                tax_amount = total_with_tax - total_without_tax
                setOutCell(wsheet, 0, 26+i, i+1)  # eilės numeris
                setOutCell(wsheet, 1, 26+i, invoice.date_invoice)
                setOutCell(wsheet, 3, 26+i, invoice.reference)
                setOutCell(wsheet, 5, 26+i, invoice.partner_id.name)
                setOutCell(wsheet, 6, 26+i, total_without_tax)
                setOutCell(wsheet, 7, 26+i, tax_amount)
                setOutCell(wsheet, 8, 26+i, total_with_tax)
                setOutCell(wsheet, 9, 26+i, amount_75)
                setOutCell(wsheet, 10, 26+i, float_round(tax_amount * 0.75, precision_digits=2))
            if platform == 'win32':
                second_part_read_loc = '\\static\\src\\representation\\Reprezentaciju nurasymo aktas 2.xls'
            else:
                second_part_read_loc = '/static/src/representation/Reprezentaciju nurasymo aktas 2.xls'
            second_part_read_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + second_part_read_loc
            rb = xlrd.open_workbook(second_part_read_loc, formatting_info=True)
            r_sheet = rb.sheet_by_index(0)
            wb, wstyle = copy2(rb)
            wsheet.merge(26 + num_acc_inv, 26 + num_acc_inv, 1, 2)
            wsheet.merge(26 + num_acc_inv, 26 + num_acc_inv, 3, 4)
            for i in range(7):
                for j in range(12):
                    wsheet.write(26 + num_acc_inv + i, j, '', get_style(r_sheet, wstyle, i, j))
                    setOutCell(wsheet, j, 26 + num_acc_inv + i, r_sheet.cell(i, j).value)
            setOutCell(wsheet, 8, 26 + num_acc_inv, Formula('SUM(I27:I%s)' % (27 + len(account_invoices)-1)))
            setOutCell(wsheet, 9, 26 + num_acc_inv, Formula('SUM(J27:J%s)' % (27 + len(account_invoices)-1)))
            setOutCell(wsheet, 10, 26 + num_acc_inv, Formula('SUM(K27:K%s)' % (27 + len(account_invoices)-1)))
            setOutCell(wsheet, 9, 26 + num_acc_inv + 6, self.env.user.company_id.findir.name)
            if num_acc_inv:  # todo delete file
                if file_num == 0:
                    write_xls.save(xls_location)
                    with open(xls_location, "rb") as f:
                        data = f.read()
                        file_1 = data.encode('base64')
                else:
                    write_xls.save(xls_location)
                    with open(xls_location, "rb") as f:
                        data = f.read()
                        file_2 = data.encode('base64')

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'reprezentacines.ataskaita.download.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'file_1': file_1,
                        'file_name_1': _('Reprezentacijų nurašymo aktas 1.xls'),
                        'file_2': file_2,
                        'file_name_2': _('Reprezentacinių nurašymo aktas 2.xls'),
                        },
        }
