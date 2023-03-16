# -*- coding: utf-8 -*-
from __future__ import division
import math
from odoo import models, api, http
import xlrd
import os
from xlutils.filter import process, XLRDReader, XLWTWriter
from odoo.http import content_disposition
from sys import platform
import cStringIO as StringIO
from odoo.http import request
import re
import unicodedata
import xlwt
import StringIO
import logging
_logger = logging.getLogger(__name__)


kwd_mark = object()
cache_styles = {}

def copy2(wb):
    w = XLWTWriter()
    process(XLRDReader(wb, 'unknown.xlsx'), w)
    return w.output[0][1], w.style_list


def _getOutCell(outSheet, colIndex, rowIndex):
    """ HACK: Extract the internal xlwt cell representation. """
    row = outSheet._Worksheet__rows.get(rowIndex)
    if not row: return None

    cell = row._Row__cells.get(colIndex)
    return cell

def getRowHeightNeeded(str, num):
    """ HACK: Based on how many chars fit into single cell, return needed height of cell for all the text to fit in """
    if len(str) <= num:
        return 256
    else:
        return int(256 * (math.ceil(len(str) / num)))  # P3:DivOK


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

def cached_easyxf(string, style):
    # if not hasattr(self, '_cached_easyxf'):
    #     self._cached_easyxf = {}
    key = (string,) + (kwd_mark,) # + tuple(sorted(kwargs.items()))
    return cache_styles.setdefault(key, style)

def get_style(inSheet, outStyle, i, j):
    xf_index = inSheet.cell_xf_index(i, j)
    return outStyle[xf_index]

class TurtoSarasasExcel:
    def __init__(self):
        self.margin = 0
        self.wb = False
        self.lines = 0
        self.nusidevejimas_line_template = False
        self.operacijos_line_template = False
        self.sheet_no = 0
        self.first_loop = True

    def load_top(self, data):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\Header.xls'
        else:
            xls_flocation = '/static/src/excel/Header.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)

        # Page Settings
        if (self.first_loop):
            base_sheet = wb.get_sheet(0)
            base_sheet.set_portrait(False)
            base_sheet.paper_size_code = 9
            base_sheet.print_scaling = 100
            base_sheet.horz_page_breaks = []
            self.wb = wb
            self.first_loop = False
            self.load_nusidevejimas_line()
            self.load_operacijos_line()
        else:
            current_sheet = rb.sheet_by_index(self.sheet_no)
            excel = self.wb
            base_sheet = excel.get_sheet(0)
            first_r_index = self.margin
            base_sheet.merge(first_r_index, first_r_index, 0, 19)  # Merge Header Title
            base_sheet.merge(first_r_index + 1, first_r_index + 1, 0, 19)  # Merge Company Info Title
            base_sheet.merge(first_r_index + 3, first_r_index + 3, 0, 2)
            base_sheet.merge(first_r_index + 4, first_r_index + 4, 0, 2)
            base_sheet.merge(first_r_index + 7, first_r_index + 7, 0, 2)
            base_sheet.merge(first_r_index + 10, first_r_index + 10, 0, 2)
            base_sheet.merge(first_r_index + 3, first_r_index + 3, 3, 7)
            base_sheet.merge(first_r_index + 4, first_r_index + 6, 3, 7)
            base_sheet.merge(first_r_index + 7, first_r_index + 9, 3, 7)
            base_sheet.merge(first_r_index + 10, first_r_index + 10, 3, 7)

            base_sheet.merge(first_r_index + 3, first_r_index + 3, 11, 16)
            base_sheet.merge(first_r_index + 4, first_r_index + 4, 11, 16)
            base_sheet.merge(first_r_index + 5, first_r_index + 5, 11, 16)

            base_sheet.merge(first_r_index + 8, first_r_index + 8, 11, 16)
            base_sheet.merge(first_r_index + 9, first_r_index + 9, 11, 16)
            base_sheet.merge(first_r_index + 10, first_r_index + 10, 11, 16)
            base_sheet.merge(first_r_index + 11, first_r_index + 11, 11, 16)

            base_sheet.merge(first_r_index + 13, first_r_index + 13, 11, 16)
            base_sheet.merge(first_r_index + 14, first_r_index + 14, 11, 16)
            base_sheet.merge(first_r_index + 15, first_r_index + 15, 11, 16)

            base_sheet.merge(first_r_index + 3, first_r_index + 3, 17, 19)
            base_sheet.merge(first_r_index + 4, first_r_index + 4, 17, 19)
            base_sheet.merge(first_r_index + 5, first_r_index + 6, 17, 19)

            base_sheet.merge(first_r_index + 8, first_r_index + 8, 17, 19)
            base_sheet.merge(first_r_index + 9, first_r_index + 9, 17, 19)
            base_sheet.merge(first_r_index + 10, first_r_index + 10, 17, 19)
            base_sheet.merge(first_r_index + 11, first_r_index + 11, 17, 19)

            base_sheet.merge(first_r_index + 13, first_r_index + 13, 17, 19)
            base_sheet.merge(first_r_index + 14, first_r_index + 14, 17, 19)
            base_sheet.merge(first_r_index + 15, first_r_index + 15, 17, 19)
            for r in xrange(current_sheet.nrows):
                for c in xrange(current_sheet.ncols):
                    cell = current_sheet.cell_value(r, c)
                    xf_index = current_sheet.cell_xf_index(r, c)
                    style = wstyle[xf_index]
                    base_sheet.write(r + self.margin, c, cell, style)

        company_info = u'{}, {}'.format(data['company_id']['display_name'] or '',
                                        data['company_id']['company_registry'] or '')
        doc_num = data['code']  or ''
        name = data['display_name']  or ''
        category = data['category_id']['display_name']  or ''
        initial_value_invoice = data['invoice_id']['reference']  or ''
        true_sale_price = data['original_value']  or ''
        purchase_date = data['pirkimo_data']  or ''
        supplier = data['partner_id']['display_name']  or ''
        purchase_price = data['value']  or ''
        date_first_depreciation = data['date_first_depreciation']  or ''
        liquidation_price = data['salvage_value']  or ''
        price_left = data['value_residual_effective'] or ''
        depreciation_period_amount = data['method_number']  or ''
        if not data['method_number']:
            yearly_salvage_percentage = ''
        else:
            yearly_salvage_percentage = (100.0 / (data['method_number'] * 12.0))  # P3:DivOK
        if data['method'] == 'linear':
            skaiciavimo_metodas = "Tiesinis"
        elif data['method'] == 'degressive':
            skaiciavimo_metodas = "Dvigubo Balanso"
        else:
            skaiciavimo_metodas = ''

        setOutCell(base_sheet, 0, self.margin + 1, company_info)
        base_sheet.row(self.margin + 1).height = getRowHeightNeeded(company_info, 120)
        setOutCell(base_sheet, 3, self.margin + 3, doc_num)
        base_sheet.row(self.margin + 3).height = getRowHeightNeeded(doc_num, 21)
        setOutCell(base_sheet, 3, self.margin + 4, name)
        base_sheet.row(self.margin + 4).height = getRowHeightNeeded(name, 21)
        setOutCell(base_sheet, 3, self.margin + 7, category)
        base_sheet.row(self.margin + 7).height = getRowHeightNeeded(category, 21)
        setOutCell(base_sheet, 3, self.margin + 10, initial_value_invoice)
        base_sheet.row(self.margin + 10).height = getRowHeightNeeded(str(initial_value_invoice), 21)

        setOutCell(base_sheet, 17, self.margin + 3, true_sale_price)
        setOutCell(base_sheet, 17, self.margin + 4, purchase_date)
        setOutCell(base_sheet, 17, self.margin + 5, supplier)

        setOutCell(base_sheet, 17, self.margin + 8, purchase_price)
        setOutCell(base_sheet, 17, self.margin + 9, date_first_depreciation)
        setOutCell(base_sheet, 17, self.margin + 10, liquidation_price)
        setOutCell(base_sheet, 17, self.margin + 11, price_left)

        setOutCell(base_sheet, 17, self.margin + 13, depreciation_period_amount)
        setOutCell(base_sheet, 17, self.margin + 14, yearly_salvage_percentage)
        setOutCell(base_sheet, 17, self.margin + 15, skaiciavimo_metodas)
        self.margin += 17

    def load_nusidevejimas_header(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\Nusidevejimas.xls'
        else:
            xls_flocation = '/static/src/excel/Nusidevejimas.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)
        current_sheet = rb.sheet_by_index(self.sheet_no)
        excel = self.wb
        base_sheet = excel.get_sheet(0)
        first_r_index = self.margin
        base_sheet.row(self.margin + 1).height = getRowHeightNeeded("Likutinė vertė laikotarpio (metų) pabaigoje", 12)
        base_sheet.merge(first_r_index, first_r_index, 0, 19) # Merge Header Title
        base_sheet.merge(first_r_index + 1, first_r_index + 2, 0, 0) # Merge Year Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 1, 4) # Merge 1st Quarter Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 5, 8) # Merge 2nd Quarter Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 9, 12) # Merge 3rd Quarter Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 13, 16)  # Merge 4th Quarter Title
        base_sheet.merge(first_r_index + 1, first_r_index + 2, 17, 17)  # Merge Yearly Amount Title
        base_sheet.merge(first_r_index + 1, first_r_index + 2, 18, 18)  # Merge Collective Wear Title
        base_sheet.merge(first_r_index + 1, first_r_index + 2, 19, 19)  # Merge Sum Left Title
        for r in xrange(current_sheet.nrows):
            for c in xrange(current_sheet.ncols):
                cell = current_sheet.cell_value(r, c)
                xf_index = current_sheet.cell_xf_index(r, c)
                style = wstyle[xf_index]
                base_sheet.write(r + self.margin, c, cell, style)
        self.margin += 3

    def load_operacijos_header(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\Operacijos.xls'
        else:
            xls_flocation = '/static/src/excel/Operacijos.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)
        current_sheet = rb.sheet_by_index(self.sheet_no)
        excel = self.wb
        base_sheet = excel.get_sheet(0)
        first_r_index = self.margin
        base_sheet.merge(first_r_index, first_r_index, 0, 19) # Merge Header Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 1, 4) # Merge Document Number Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 5, 8)  # Merge Type Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 9, 12)  # Merge Initial Value Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 13, 16)  # Merge Wear Title
        base_sheet.merge(first_r_index + 1, first_r_index + 1, 18, 19)  # Merge Responsible Person Title
        for r in xrange(current_sheet.nrows):
            for c in xrange(current_sheet.ncols):
                cell = current_sheet.cell_value(r, c)
                xf_index = current_sheet.cell_xf_index(r, c)
                style = wstyle[xf_index]
                base_sheet.write(r + self.margin, c, cell, style)
        base_sheet.row(self.margin + 1).height = 256 * 2

        self.margin += 2

    def load_nusidevejimas_line(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\Nusidevejimas_line.xls'
        else:
            xls_flocation = '/static/src/excel/Nusidevejimas_line.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        self.nusidevejimas_line_template = rb

    def load_operacijos_line(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\Operacijos_line.xls'
        else:
            xls_flocation = '/static/src/excel/Operacijos_line.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        self.operacijos_line_template = rb

    def write_nusidevejimas_line(self, data):
        new_sheet = self.nusidevejimas_line_template.sheet_by_index(self.sheet_no)
        base_sheet = self.wb.get_sheet(0)
        style_wb, style_style = copy2(self.nusidevejimas_line_template)
        for r in xrange(new_sheet.nrows):
            for c in xrange(new_sheet.ncols):
                xf_index = new_sheet.cell_xf_index(r, c)
                cell_style = style_style[xf_index]
                cell = new_sheet.cell_value(r, c)
                base_sheet.write(r + self.margin, c, cell, cell_style)

        setOutCell(base_sheet, 0, self.margin, data['year'])
        setOutCell(base_sheet, 1, self.margin, data['month_1'])
        setOutCell(base_sheet, 2, self.margin, data['month_2'])
        setOutCell(base_sheet, 3, self.margin, data['month_3'])
        setOutCell(base_sheet, 4, self.margin, data['quarter_1_sum'])
        setOutCell(base_sheet, 5, self.margin, data['month_4'])
        setOutCell(base_sheet, 6, self.margin, data['month_5'])
        setOutCell(base_sheet, 7, self.margin, data['month_6'])
        setOutCell(base_sheet, 8, self.margin, data['quarter_2_sum'])
        setOutCell(base_sheet, 9, self.margin, data['month_7'])
        setOutCell(base_sheet, 10, self.margin, data['month_8'])
        setOutCell(base_sheet, 11, self.margin, data['month_9'])
        setOutCell(base_sheet, 12, self.margin, data['quarter_3_sum'])
        setOutCell(base_sheet, 13, self.margin, data['month_10'])
        setOutCell(base_sheet, 14, self.margin, data['month_11'])
        setOutCell(base_sheet, 15, self.margin, data['month_12'])
        setOutCell(base_sheet, 16, self.margin, data['quarter_4_sum'])
        setOutCell(base_sheet, 17, self.margin, data['yearly_sum'])
        setOutCell(base_sheet, 18, self.margin, data['wear_sum'])
        setOutCell(base_sheet, 19, self.margin, data['end_of_period_sum'])

        self.margin += 1
        self.lines += 1

    def write_operacijos_line(self, data):
        new_sheet = self.operacijos_line_template.sheet_by_index(self.sheet_no)
        base_sheet = self.wb.get_sheet(0)
        style_wb, style_style = copy2(self.operacijos_line_template)
        first_r_index = self.margin
        base_sheet.merge(first_r_index, first_r_index, 1, 4)
        base_sheet.merge(first_r_index, first_r_index, 5, 8)
        base_sheet.merge(first_r_index, first_r_index, 9, 12)
        base_sheet.merge(first_r_index, first_r_index, 13, 16)
        base_sheet.merge(first_r_index, first_r_index, 18, 19)
        for r in xrange(new_sheet.nrows):
            for c in xrange(new_sheet.ncols):
                xf_index = new_sheet.cell_xf_index(r, c)
                cell_style = style_style[xf_index]
                cell = new_sheet.cell_value(r, c)
                base_sheet.write(r + self.margin, c, cell, cell_style)
        setOutCell(base_sheet, 0, self.margin, data['date'])
        setOutCell(base_sheet, 1, self.margin, data['doc_id'])
        setOutCell(base_sheet, 5, self.margin, data['type'])
        setOutCell(base_sheet, 9, self.margin, data['init_value'])
        setOutCell(base_sheet, 13, self.margin, data['transactions'])
        setOutCell(base_sheet, 17, self.margin, data['upgrades'])
        setOutCell(base_sheet, 18, self.margin, data['person_in_charge'])
        self.margin += 1
        self.lines += 1

    def export(self):
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')

class AccountAssetAsset(models.Model):
    _inherit = "account.asset.asset"

    @api.multi
    def export_excel(self, data=False):
        excel = TurtoSarasasExcel()
        page_breaks = list()
        margin_written = False
        for rec in self:
            excel.load_top(rec)
            excel.load_operacijos_header()
            operacijos = []
            init_value = 0.00
            if rec.invoice_id:
                ref = ''
                if rec.invoice_id.reference:
                    ref = rec.invoice_id.reference
                details = {
                    'date': rec.invoice_id.date_invoice, #TODO: pasitarti su buhalteriu
                    'doc_id': ref,
                    'type': 'Pirkimas',
                    'init_value': init_value,
                    'transactions': rec.invoice_id.residual,
                    'upgrades': '0',
                    'person_in_charge': rec.invoice_id.user_id.display_name, #TODO: Atsakingo asmens pasikeitimo operacija
                }
                operacijos.append(details)
                init_value += rec.invoice_id.residual
            for line in rec['change_line_ids']:
                ref = ''
                if line.invoice_ids:
                    ref = '; '.join(line.mapped('invoice_ids.reference'))

                details = {
                    'date': line.date,
                    'doc_id': ref,
                    'type': 'Pagerinimas',
                    'init_value': init_value,
                    'transactions': '0',
                    'upgrades': line.change_amount,
                    'person_in_charge': ''
                }
                operacijos.append(details)
                init_value += line.change_amount
            if rec.date_close:
                details = {
                    'date': rec.date_close,
                    'doc_id': '',
                    'type': unicode('Nurašymas'),
                    'init_value': init_value,
                    'transactions': init_value * -1,
                    'upgrades': '0',
                    'person_in_charge': '',
                }
                operacijos.append(details)
                init_value = 0
            if rec.sale_invoice_id:
                details = {
                    'date': rec.sale_invoice_id.date_invoice,
                    'doc_id': rec.sale_invoice_id.number or '-',
                    'type': 'Pardavimas',
                    'init_value': init_value,
                    'transactions': rec.sale_invoice_id.amount_total * -1,
                    'upgrades': '0',
                    'person_in_charge': rec.sale_invoice_id.user_id.display_name,
                }
                operacijos.append(details)
                init_value += rec.sale_invoice_id.amount_total * -1
            operacijos = sorted(operacijos, key=lambda r: r['date'])
            for i in range(0, len(operacijos)):
                excel.write_operacijos_line(operacijos[i])
            excel.margin += 1
            excel.load_nusidevejimas_header()
            current_year = False
            total_depreciation_sum = 0
            month_sum = [0 for i in range(12)]
            end_of_period_sum = rec.value
            year = False
            for line in rec['depreciation_line_ids'].filtered(lambda r: r.move_check).sorted(lambda r: r.depreciation_date):
                year, month, day = line['depreciation_date'].split('-')
                if not current_year:
                    current_year = year
                if current_year != year:
                    quarter_1_sum = month_sum[0] + month_sum[1] + month_sum[2]
                    quarter_2_sum = month_sum[3] + month_sum[4] + month_sum[5]
                    quarter_3_sum = month_sum[6] + month_sum[7] + month_sum[8]
                    quarter_4_sum = month_sum[9] + month_sum[10] + month_sum[11]
                    year_sum = quarter_1_sum + quarter_2_sum + quarter_3_sum + quarter_4_sum
                    end_of_period_sum -= year_sum
                    total_depreciation_sum = total_depreciation_sum + year_sum
                    for i in range(0, 12):
                        if month_sum[i] == 0:
                            month_sum[i] = ''
                    if quarter_1_sum == 0: quarter_1_sum = ''
                    if quarter_2_sum == 0: quarter_2_sum = ''
                    if quarter_3_sum == 0: quarter_3_sum = ''
                    if quarter_4_sum == 0: quarter_4_sum = ''
                    details = {
                        'year': current_year,
                        'month_1': month_sum[0],
                        'month_2': month_sum[1],
                        'month_3': month_sum[2],
                        'month_4': month_sum[3],
                        'month_5': month_sum[4],
                        'month_6': month_sum[5],
                        'month_7': month_sum[6],
                        'month_8': month_sum[7],
                        'month_9': month_sum[8],
                        'month_10': month_sum[9],
                        'month_11': month_sum[10],
                        'month_12': month_sum[11],
                        'quarter_1_sum': quarter_1_sum,
                        'quarter_2_sum': quarter_2_sum,
                        'quarter_3_sum': quarter_3_sum,
                        'quarter_4_sum': quarter_4_sum,
                        'yearly_sum': year_sum,
                        'wear_sum': total_depreciation_sum,
                        'end_of_period_sum': end_of_period_sum,
                    }
                    current_year = year
                    excel.write_nusidevejimas_line(details)
                    for i in range(0, 12):
                        month_sum[i] = 0
                month_sum[int(month) - 1] = month_sum[int(month) - 1] + line['amount']
            if len(rec['depreciation_line_ids'].filtered(lambda r: r.move_check).sorted(lambda r: r.depreciation_date)) != 0:
                quarter_1_sum = month_sum[0] + month_sum[1] + month_sum[2]
                quarter_2_sum = month_sum[3] + month_sum[4] + month_sum[5]
                quarter_3_sum = month_sum[6] + month_sum[7] + month_sum[8]
                quarter_4_sum = month_sum[9] + month_sum[10] + month_sum[11]
                year_sum = quarter_1_sum + quarter_2_sum + quarter_3_sum + quarter_4_sum
                end_of_period_sum -= year_sum
                total_depreciation_sum = total_depreciation_sum + year_sum
                for i in range(0, 12):
                    if month_sum[i] == 0:
                        month_sum[i] = ''
                if quarter_1_sum == 0: quarter_1_sum = ''
                if quarter_2_sum == 0: quarter_2_sum = ''
                if quarter_3_sum == 0: quarter_3_sum = ''
                if quarter_4_sum == 0: quarter_4_sum = ''
                details = {
                    'year': current_year,
                    'month_1': month_sum[0],
                    'month_2': month_sum[1],
                    'month_3': month_sum[2],
                    'month_4': month_sum[3],
                    'month_5': month_sum[4],
                    'month_6': month_sum[5],
                    'month_7': month_sum[6],
                    'month_8': month_sum[7],
                    'month_9': month_sum[8],
                    'month_10': month_sum[9],
                    'month_11': month_sum[10],
                    'month_12': month_sum[11],
                    'quarter_1_sum': quarter_1_sum,
                    'quarter_2_sum': quarter_2_sum,
                    'quarter_3_sum': quarter_3_sum,
                    'quarter_4_sum': quarter_4_sum,
                    'yearly_sum': year_sum,
                    'wear_sum': total_depreciation_sum,
                    'end_of_period_sum': end_of_period_sum,
                }
                current_year = year
                excel.write_nusidevejimas_line(details)
                for i in range(0, 12):
                    month_sum[i] = 0

            excel.margin += 2
            page_breaks.append((excel.margin, 0, 0))

        base_sheet = excel.wb.get_sheet(0)
        base_sheet.horz_page_breaks = page_breaks

        base64_file = excel.export()
        filename = 'ilgalaikio_turto_sarasas_.xls'
        if data:
            filename = 'ilgalaikio_turto_sarasas_(' + data['form']['date_from'] + '_' + data['form']['date_to'] + ').xls'
        attach_id = self.env['ir.attachment'].sudo().create({
            'res_model': 'account.asset.asset',
            'res_id': self[0].id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        if self._context.get('archive', False):
            return base64_file
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=account.asset.asset&res_id=%s&attach_id=%s' % (self[0].id, attach_id.id),
            'target': 'self',
        }

    @api.model
    def create_excel_export_action(self):
        action = self.env.ref('ilgalaikis_turtas.check_advanced_report')
        if action:
            action.create_action()


AccountAssetAsset()


class BinaryDownload(http.Controller):
    @http.route('/web/binary/download', type='http', auth='user')
    def download(self, res_model, res_id, attach_id, **kw):
        if res_model:
            try:
                request.env[res_model].check_access_rights('read')
            except:
                allow = False
            else:
                allow = True
            if request.env.user.is_hr_manager():
                allow = True
            if not allow:
                return request.not_found()
            attachment_obj = request.env['ir.attachment'].sudo()
            if not res_model or not res_id:
                return request.not_found()
            if attach_id:
                attachment_id = attachment_obj.search([('res_model', '=', res_model), ('res_id', '=', res_id),
                                                       ('id', '=', attach_id)],
                                                      order='id desc', limit=1)
            else:
                attachment_id = attachment_obj.search([('res_model', '=', res_model), ('res_id', '=', res_id)],
                                                      order='id desc', limit=1)
            if attachment_id:
                filename = attachment_id.datas_fname
                headers = [
                    ('Content-Type', 'application/octet-stream; charset=binary'),
                    ('Content-Disposition', content_disposition(filename)),
                ]
                attach_bin = attachment_id.datas.decode('base64')
                if attachment_id.res_model:
                    attachment_model = request.env[attachment_id.res_model]
                    if attachment_model.sudo()._name == 'res.company' or attachment_model.sudo()._transient:
                        attachment_id.sudo().unlink()
                return request.make_response(attach_bin, headers)
        else:
            return request.not_found()


BinaryDownload()
