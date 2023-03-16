# -*- coding: utf-8 -*-
from datetime import datetime, date
from sys import platform
import os
from xlutils.filter import process, XLRDReader, XLWTWriter
from xlsxwriter.utility import xl_col_to_name
import xlrd
import xlwt

import cStringIO as StringIO

from odoo import tools
from dateutil.relativedelta import relativedelta

_HORIZONTAL_WRITE_LINE = 7
_FIRST_HEADER_POS = (3, 5)
_NEXT_HEADER_STEP = 2

_FILE_QUARTER = 'quarter_template_new.xls'
_FILE_TOTAL = 'total_template_new.xls'

_MATERIAL_TYPE = (('metalas', 'Metalas'), ('plastikas', 'Plastikas'), ('stiklas', 'Stiklas'), ('popierius', 'Popierius'),
                    ('medis', 'Medis'), ('pet', 'PET'), ('kombinuota', 'Kombinuota'), ('kita', 'Kita'))
_PACKAGE_CATEGORY = (('pirmine', u'Prekinė (pirminė)'), ('antrine', u'Grupinė (antrinė)'), ('tretine', u'Transporto (tretinė)'))


_HEADER_X_NAME = 'Kiekis'
_HEADER_Y_NAME = 'Svoris, kg'
_COLUMN_HEADER_WIDTH = 3300  # uom??


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


def getQuarterStart(dt=datetime.utcnow()):
    return datetime(dt.year, (dt.month - 1) // 3 * 3 + 1, 1)


class PackagesExcel:
    def __init__(self, model_object, date_from, date_to, group_column_name):
        self.workbook = False
        self.object = model_object
        self.main_sheet = False
        self.quater_sheets = []
        self._default_write_line_nbr = _HORIZONTAL_WRITE_LINE  #from 0
        self._main_sheet_write_line = self._default_write_line_nbr
        self._quarter_sheets_write_lines = {}
        self.quarter_template_sheet = False

        self.quarter_template_document = False
        self.quarter_template_style = False

        # totals on the left
        self.group_column_name = group_column_name
        self.group_column_name_position = 0  # totals position, calculated the header is completed

        self.number_format_string = '# ##0.00'

        self.name_combinations = []  # columns to display

        self._build_excel(date_from, date_to)

    def _get_main_sheet(self):
        return self.wb.get_sheet(0)

    def _copy_static_form(self, name):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\'+name
        else:
            xls_flocation = '/static/src/excel/'+name
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, style = copy2(rb)
        return rb, wb, style

    def _prepare_main_sheet(self, date_from, date_to):
        setOutCell(self.main_sheet, 0, 0, self.object.company_id.name or '')
        setOutCell(self.main_sheet, 0, 2, 'nuo ' + date_from + ' iki ' + date_to)
        setOutCell(self.main_sheet, 0, 3, self.group_column_name)
        # setOutCell(self.main_sheet, self.group_column_name_position, 5, self.group_column_name)

    def _copy_sheet(self, template, new_sheet):
        for merges in template.merged_cells:
            new_sheet.merge(merges[0], merges[1]-1, merges[2], merges[3]-1)
        for row in xrange(template.nrows):
            for col in xrange(template.ncols):
                xf_index = template.cell_xf_index(row, col)
                cell_style = self.quarter_template_style[xf_index]
                new_sheet.write(row, col, template.cell_value(row, col), cell_style)

    def _create_sheet(self, sheet_name, template):
        new_sheet = self.wb.add_sheet(sheet_name, cell_overwrite_ok=True)
        self._copy_sheet(template, new_sheet)
        self._prepare_quarter_sheet(new_sheet, sheet_name)  # move outside
        return new_sheet

    def _create_quarter_sheets(self, date_from, date_to):
        start_date = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

        quarter_sheets = []
        quarter_names = ['I ketv.', 'II ketv.', 'III ketv.', 'IV ketv.']

        quarter_start = getQuarterStart(start_date)
        start_year = quarter_start.year
        quarter_start_id = (quarter_start.month-1)//3
        sheet_name = str(start_year) + ' ' + quarter_names[quarter_start_id]
        quarter_sheets.append({
            'sheet': self._create_sheet(sheet_name, self.quarter_template_sheet),
            'period_start': start_date,
            'period_end': quarter_start + relativedelta(months=2, day=31)
        })
        quarter_date = quarter_start
        while quarter_date + relativedelta(months=3, day=1) <= end_date:
            quarter_date = quarter_date + relativedelta(months=3, day=1)
            quarter_id = (quarter_date.month-1)//3
            sheet_name = str(quarter_date.year) + ' ' + quarter_names[quarter_id]
            quarter_sheets.append({
                'sheet': self._create_sheet(sheet_name, self.quarter_template_sheet),
                'period_start': quarter_date,
                'period_end': quarter_date + relativedelta(months=2, day=31) if quarter_date + relativedelta(months=2, day=31) <= end_date else end_date
            })

        return quarter_sheets

    def _get_quarter_template_sheet(self):
        self.quarter_template_document, tmp, self.quarter_template_style = self._copy_static_form(_FILE_QUARTER)
        return self.quarter_template_document.sheet_by_index(0)

    def _prepare_quarter_sheet(self, sheet, name):
            setOutCell(sheet, 0, 0, self.object.company_id.name or '')
            setOutCell(sheet, 0, 2, name)
            setOutCell(sheet, 0, 3, self.group_column_name)
            # setOutCell(sheet, self.group_column_name_position, 5, self.group_column_name)
            # copy columns' width from  main sheet
            for indx in self.main_sheet.cols:
                sheet.col(indx).set_width(self.main_sheet.cols[indx].width)
            for indx in self.main_sheet.rows:
                sheet.row(indx).height = self.main_sheet.rows[indx].height

    def _build_excel(self, date_from, date_to):
        original_document, wb, wstyle = self._copy_static_form(_FILE_TOTAL)
        self.wb = wb

        self.main_sheet_style = wstyle
        self.main_sheet_template = original_document.sheet_by_index(0)

        self.main_sheet = self._get_main_sheet()
        self._prepare_main_sheet(date_from, date_to)

        # start creating new sheets
        self.quarter_template_sheet = self._get_quarter_template_sheet()
        self.quater_sheets = self._create_quarter_sheets(date_from, date_to)

    def _write_cell(self, row, col, name, style, sheet, template, is_number=False):
        # cell style only from _FIRST_HEADER_POS[0] if col greater -> min
        xf_index = template.cell_xf_index(self._default_write_line_nbr, min(col, _FIRST_HEADER_POS[0]))
        cell_style = style[xf_index]
        if is_number:
            cell_style.num_format_str = self.number_format_string
        sheet.write(row, col, name or '', cell_style)

    def _write_pair_cells(self, field, template, style, sheet, row, col, package, is_number=False):
        if field in package and package[field]['nbr'] > 0:
            self._write_cell(row, col, package[field]['nbr'], style, sheet, template, is_number)
            self._write_cell(row, col+1, package[field]['weight'], style, sheet, template, is_number)
        else:
            self._write_cell(row, col, '', style, sheet, template)
            self._write_cell(row, col+1, '', style, sheet, template)

    def _copy_row(self, template, style, sheet, row, package):
        #col = 0 Tiekejas
        self._write_cell(row, 0, package['partner'], style, sheet, template)
        #col = 1 Dok nr
        self._write_cell(row, 1, package['doc_nbr'], style, sheet, template)
        #col = 2 date
        self._write_cell(row, 2, package['date'], style, sheet, template)

        indx = 0
        for col in self.name_combinations:
            self._write_pair_cells(col[1], template, style, sheet, row, 3+indx, package, True)
            indx += 2

        # # col = 3,4 popierine pirmine
        # self._write_pair_cells('pirmine_popierius', template, style, sheet, row, 3, package, True)
        # # col = 5,6 plastikas pirmine
        # self._write_pair_cells('pirmine_plastikas', template, style, sheet, row, 5, package, True)
        # # col = 7,8 popierius antrine
        # self._write_pair_cells('antrine_popierius', template, style, sheet, row, 7, package, True)
        # # col = 9,10 plastikas antrine
        # self._write_pair_cells('antrine_plastikas', template, style, sheet, row, 9, package, True)
        # # col = 11,12 kombinuota pirmine
        # self._write_pair_cells('pirmine_medis', template, style, sheet, row, 11, package, True)
        # # col = 13,14 kombinuota antrine
        # self._write_pair_cells('antrine_medis', template, style, sheet, row, 13, package, True)
        # # col = 15,16 mataline pirmine
        # self._write_pair_cells('pirmine_metalas', template, style, sheet, row, 15, package, True)
        # # col = 17,18 metaline antrine
        # self._write_pair_cells('antrine_metalas', template, style, sheet, row, 17, package, True)
        # ROBO: change

    def _write_main_sheet_line(self, package):
        if package['print_line']:
            self._copy_row(self.main_sheet_template, self.main_sheet_style, self.main_sheet, self._main_sheet_write_line, package)
            self._main_sheet_write_line += 1

    def _write_quarter_sheet_line(self, package):
        if package['print_line']:
            date = datetime.strptime(package['date'], tools.DEFAULT_SERVER_DATE_FORMAT)
            for indx, sheet in enumerate(self.quater_sheets):
                if sheet['period_start'] <= date <= sheet['period_end']:
                    if indx not in self._quarter_sheets_write_lines:
                        self._quarter_sheets_write_lines[indx] = self._default_write_line_nbr
                    self._copy_row(self.quarter_template_sheet, self.quarter_template_style, sheet['sheet'], self._quarter_sheets_write_lines[indx], package)
                    self._quarter_sheets_write_lines[indx] += 1
                    break

    def _add_total_below(self, row, sheet):
        if row == self._default_write_line_nbr:
            return
        sheet.merge(row, row, 0, 2)

        style = xlwt.XFStyle()
        style.font.bold = True
        style.alignment.horz = 3
        sheet.write(row, 0, 'Viso:', style)

        style.alignment.hoz = 0
        style.num_format_str = self.number_format_string

        # ROBO: change
        for indx in xrange(len(self.name_combinations)*2+2):
            start_pos = _FIRST_HEADER_POS[0]
            letter = xl_col_to_name(start_pos+indx)
            sum_str = 'SUM('+letter+str(self._default_write_line_nbr+1)+':'+letter+'%s)'% row
            sheet.write(row, start_pos+indx, xlwt.Formula(sum_str), style)

    def _add_total_right(self, row, sheet):
        if row == self._default_write_line_nbr:
            return
        style = xlwt.XFStyle()
        style.font.bold = True
        style.borders.top = 1
        style.borders.bottom = 1
        style.borders.left = 1
        style.borders.right = 1
        style.num_format_str = self.number_format_string

        # ROBO: change letters and group_column_name_position?
        start_pos = _FIRST_HEADER_POS[1]+1+1  # +1 - row below; +1 Formula true index
        nbr_col = len(self.name_combinations)

        def _formula_string(start=3):
            formula_string = 'SUM('
            for i in range(0, len(self.name_combinations)):
                formula_string += xl_col_to_name(start)
                formula_string += '%s;'
                start += 2
            formula_string += ')'
            return formula_string

        sum_kiekis_formula = _formula_string(_FIRST_HEADER_POS[0])
        sum_svoris_formula = _formula_string(_FIRST_HEADER_POS[0]+1)

        for indx in xrange(start_pos, row):
            sum_str = sum_kiekis_formula % ((indx+1,) * nbr_col)
            sheet.write(indx, self.group_column_name_position, xlwt.Formula(sum_str), style)

            sum_str = sum_svoris_formula % ((indx+1,) * nbr_col)
            sheet.write(indx, self.group_column_name_position+1, xlwt.Formula(sum_str), style)

    def _add_total_lines_with_formulas_main(self):
        self._add_total_below(self._main_sheet_write_line, self.main_sheet)
        self._add_total_right(self._main_sheet_write_line, self.main_sheet)

    def _add_total_lines_with_formulas_quarters(self):
        for indx, sheet in enumerate(self.quater_sheets):
            if indx in self._quarter_sheets_write_lines:
                self._add_total_below(self._quarter_sheets_write_lines[indx], sheet['sheet'])
                self._add_total_right(self._quarter_sheets_write_lines[indx], sheet['sheet'])

    def _add_total_lines_with_formulas(self):
        self._add_total_lines_with_formulas_main()
        self._add_total_lines_with_formulas_quarters()

    # HEADER work point
    def _write_header(self, pos, name):
        style = xlwt.XFStyle()
        style.borders.bottom = 1
        setOutCell(self.main_sheet, pos[0], pos[1], name)
        self.main_sheet.write(pos[1]-1, pos[0]+1, '', style)
        self.main_sheet.merge(pos[1], pos[1], pos[0], pos[0]+1)
        for sheet in self.quater_sheets:
            setOutCell(sheet['sheet'], pos[0], pos[1], name)
            sheet['sheet'].merge(pos[1], pos[1], pos[0], pos[0] + 1)
            sheet['sheet'].write(pos[1] - 1, pos[0] + 1, '', style)

    def _copy_header(self, orig_pos, next_pos):

        def _copy_header_cell(shift_pos_x=0, shift_pos_y=0, name=''):
            # main template
            xf_index = self.main_sheet_template.cell_xf_index(orig_pos[0] + shift_pos_x, orig_pos[1] + shift_pos_y)
            cell_style = self.main_sheet_style[xf_index]
            cell_style.borders.bottom = 1
            cell_style.borders.top = 1
            self.main_sheet.write(next_pos[0] + shift_pos_x, next_pos[1] + shift_pos_y, name, cell_style)
            # quarter templates
            xf_index = self.quarter_template_sheet.cell_xf_index(orig_pos[0] + shift_pos_x, orig_pos[1] + shift_pos_y)
            cell_style = self.quarter_template_style[xf_index]
            cell_style.borders.bottom = 1
            cell_style.borders.top = 1
            for sheet in self.quater_sheets:
                sheet['sheet'].write(next_pos[0] + shift_pos_x, next_pos[1] + shift_pos_y, name, cell_style)

        _copy_header_cell(shift_pos_x=0, shift_pos_y=0, name='')
        # _copy_header_cell(shift_pos_x=0, shift_pos_y=1, name='')
        _copy_header_cell(shift_pos_x=1, shift_pos_y=0, name=_HEADER_X_NAME)
        _copy_header_cell(shift_pos_x=1, shift_pos_y=1, name=_HEADER_Y_NAME)
        # copy style of two cells bellow header
        # _copy_header_cell(shift_pos_x=2, shift_pos_y=0, name='')
        # _copy_header_cell(shift_pos_x=2, shift_pos_y=1, name='')

        # column width
        self.main_sheet.col(next_pos[1]).set_width(_COLUMN_HEADER_WIDTH)
        self.main_sheet.col(next_pos[1] + 1).set_width(_COLUMN_HEADER_WIDTH)
        for sheet in self.quater_sheets:
            sheet['sheet'].col(next_pos[1]).set_width(_COLUMN_HEADER_WIDTH)
            sheet['sheet'].col(next_pos[1] + 1).set_width(_COLUMN_HEADER_WIDTH)

    def _prepare_sheets_header(self, lines, non_zero_columns=False):
        # ROBO: Posibility to reorder here
        all_combinations = [(x[1] + ' ' + y[1], x[0]+'_'+y[0]) for y in _MATERIAL_TYPE for x in _PACKAGE_CATEGORY]

        # filter out zero columns
        if non_zero_columns:
            all_columns = dict((k[1], True) for k in all_combinations)
            for row in lines.values():
                for key in row.keys():
                    if all_columns.get(key, False):
                        all_columns[key] = False
            all_combinations = [x for x in all_combinations if not all_columns[x[1]]]

        header_position = _FIRST_HEADER_POS
        self.name_combinations = all_combinations

        # calculate total column on the right position
        self.group_column_name_position = _FIRST_HEADER_POS[0]+len(all_combinations)*2

        for indx, name in enumerate(all_combinations):
            self._write_header(header_position, name[0])
            header_position = (header_position[0] + _NEXT_HEADER_STEP, header_position[1])
            # (row, col) switch for different functions
            # last one for totals on the right
            self._copy_header((_FIRST_HEADER_POS[1], _FIRST_HEADER_POS[0]), (header_position[1], header_position[0]))

        # name of the totals on the left with merge: quoters and total sheets
        setOutCell(self.main_sheet, self.group_column_name_position, _FIRST_HEADER_POS[1], self.group_column_name)
        self.main_sheet.merge(_FIRST_HEADER_POS[1], _FIRST_HEADER_POS[1], self.group_column_name_position, self.group_column_name_position + 1)

        #last left border
        style = xlwt.XFStyle()
        style.borders.left = 1
        style2 = xlwt.XFStyle()
        style2.borders.bottom = 1
        self.main_sheet.write(_FIRST_HEADER_POS[1], self.group_column_name_position+2, '', style)
        self.main_sheet.write(_FIRST_HEADER_POS[1]-1, self.group_column_name_position+1, '', style2)

        for sheet in self.quater_sheets:
            setOutCell(sheet['sheet'], self.group_column_name_position, _FIRST_HEADER_POS[1], self.group_column_name)
            sheet['sheet'].merge(_FIRST_HEADER_POS[1], _FIRST_HEADER_POS[1], self.group_column_name_position, self.group_column_name_position + 1)
            # last left border
            sheet['sheet'].write(_FIRST_HEADER_POS[1], self.group_column_name_position + 2, '', style)
            sheet['sheet'].write(_FIRST_HEADER_POS[1]-1, self.group_column_name_position + 1, '', style2)


    # API

    def export(self):
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')

    def write_lines(self, lines, non_zero_columns=False):
        # regain quarter template
        self.quarter_template_sheet = self._get_quarter_template_sheet()
        self._prepare_sheets_header(lines, non_zero_columns=non_zero_columns)
        for picking_id in lines:
            self._write_main_sheet_line(lines[picking_id])
            self._write_quarter_sheet_line(lines[picking_id])
        self._add_total_lines_with_formulas()
