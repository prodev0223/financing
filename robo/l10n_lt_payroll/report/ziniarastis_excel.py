# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, tools, _, http, fields, exceptions
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import xlrd
import os
from xlutils.filter import process, XLRDReader, XLWTWriter
from odoo.http import request, content_disposition
from sys import platform
import xlwt
import copy
import cStringIO as StringIO


NEATVYKIMAI_LIST = ['V', 'M', 'D', 'L', 'N', 'NS', 'A', 'MA', 'NA', 'KA', 'G', 'ID', 'PV',
                    'MD', 'K', 'SŽ', 'KV', 'KVN', 'VV', 'KT', 'KM', 'PK', 'PN', 'PB', 'ND', 'NP', 'KR',
                    'NN', 'ST', 'TA', 'P', 'MP', 'NLL']

NEATVYKIMAI_BE_K = ['V', 'M', 'MP', 'NLL', 'D', 'L', 'N', 'NS', 'A', 'MA', 'NA', 'KA', 'G', 'ID', 'PV',
                    'MD', 'SŽ', 'KV', 'KVN', 'VV', 'KT', 'KM', 'PK', 'PN', 'PB', 'ND', 'NP', 'KR',
                    'NN', 'ST', 'TA', 'P']


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


class ZiniarastisExcel:
    def __init__(self, model_object, date_dt=datetime.utcnow(), fit_lines=10, holidays=None, weekends=None):
        sheets = [3, 2, 1, 0]
        self.sheet_no = sheets[(date_dt + relativedelta(day=31)).day - 28]
        self.margin = 0
        self.wb = False
        self.lines = 0
        self.fit_lines = fit_lines
        self.line_template = False
        self.object = model_object
        self.holidays = holidays or []
        self.weekends = weekends or []
        self.holiday_cols = []
        self.weekend_cols = []

        self.totals = [0 for i in xrange(12)]
        self.totals_dict = dict(
            (key, [0, 0]) for key in NEATVYKIMAI_LIST)

        self.load_top(date_dt)
        self.load_header()
        self.load_line()
        self.dict_sort = NEATVYKIMAI_LIST

    def load_top(self, date_dt):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\top.xls'
        else:
            xls_flocation = '/static/src/excel/top.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)
        sheet = wb.get_sheet(0)
        # Page Settings
        sheet.set_portrait(False)
        sheet.paper_size_code = 9
        sheet.print_scaling = 65
        sheet.horz_page_breaks = []

        period = u'%s METŲ %s' % (date_dt.year, str(date_dt.month).zfill(2))
        setOutCell(sheet, 15, 4, self.object.company_id.name or '')
        setOutCell(sheet, 16, 6, self.object.company_id.company_registry or '')
        setOutCell(sheet, 14, 9, period)
        self.wb = wb
        self.margin += 12

    def load_header(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\header.xls'
        else:
            xls_flocation = '/static/src/excel/header.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        sheet = rb.sheet_by_index(self.sheet_no)
        excel = self.wb
        sheet2 = excel.get_sheet(0)
        style_wb, style_style = copy2(rb)
        for r in xrange(sheet.nrows):
            for c in xrange(sheet.ncols):
                cell = sheet.cell_value(r, c)
                xf_index = sheet.cell_xf_index(r, c)
                cell_style = style_style[xf_index]
                if r >= 4:# and sheet.ncols - 12 >= c >= 6:
                    day_col = False
                    try:
                        int(cell)
                        day_col = True
                    except:
                        pass
                    if day_col and int(cell) in self.holidays and r ==4:
                        # cell_style = copy.deepcopy(cell_style)
                        # pattern = xlwt.Pattern()
                        # pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                        # pattern.pattern_fore_colour = xlwt.Style.colour_map['tan']
                        # cell_style.pattern = pattern
                        # sheet2.write(r + self.margin, c, cell, cell_style)
                        self.holiday_cols.append(c)
                        # continue
                    elif day_col and int(cell) in self.weekends and r == 4:
                        # cell_style = copy.deepcopy(cell_style)
                        # pattern = xlwt.Pattern()
                        # pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                        # pattern.pattern_fore_colour = xlwt.Style.colour_map['gray25']
                        # cell_style.pattern = pattern
                        # sheet2.write(r + self.margin, c, cell, cell_style)
                        self.weekend_cols.append(c)
                        # continue
                    if c in self.holiday_cols:
                        cell_style = copy.deepcopy(cell_style)
                        pattern = xlwt.Pattern()
                        pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                        pattern.pattern_fore_colour = xlwt.Style.colour_map['tan']
                        cell_style.pattern = pattern
                        sheet2.write(r + self.margin, c, cell, cell_style)
                        continue
                    elif c in self.weekend_cols:
                        cell_style = copy.deepcopy(cell_style)
                        pattern = xlwt.Pattern()
                        pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                        pattern.pattern_fore_colour = xlwt.Style.colour_map['gray25']
                        cell_style.pattern = pattern
                        sheet2.write(r + self.margin, c, cell, cell_style)
                        continue
                sheet2.write(r + self.margin, c, cell, cell_style)
        self.margin += 7
        return True

    def load_line(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\line.xls'
        else:
            xls_flocation = '/static/src/excel/line.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        self.line_template = rb

    def write_line(self, data):
        sheet = self.line_template.sheet_by_index(self.sheet_no)
        sheet2 = self.wb.get_sheet(0)
        if self.lines > 0 and self.lines % self.fit_lines == 0:
            sheet2.horz_page_breaks.append([self.margin, 0, 50])
            self.load_header()
        style_wb, style_style = copy2(self.line_template)
        r_len = len(data)
        first_r_index = self.margin  # darbuotojo pareigos
        sheet2.merge(first_r_index, first_r_index + 2, 3, 3)
        for r in xrange(sheet.nrows):
            if r < r_len:
                row = data[r]
                c_len = len(row)
            else:
                row = False
                c_len = -1
            for c in xrange(sheet.ncols):
                if c < c_len and row:
                    cell = row[c]
                else:
                    cell = ''
                # --- Process information ---
                if cell and -1 >= (c - c_len + 1) >= -12:
                    try:
                        number = float(cell)
                        self.totals[c - c_len + 1] += number
                    except:
                        try:
                            for n in cell.split('\n'):
                                n = float(n)
                                self.totals[c - c_len + 1] += n
                        except:
                            pass
                elif cell and (c - c_len) < -12 and c > 5:
                    try:
                        new_cell = ''
                        for mark in cell.split(', '):
                            if new_cell:
                                new_cell += ' '
                            number = mark.split(' ')
                            if len(number) == 1:
                                # EDGE CASE, sometimes codes are printed out in the next multiple rows. Did not
                                # investigate in which cases this happens.
                                try:
                                    number = float(number[0])
                                    other_magic_cell = data[r + 2][c]
                                    if other_magic_cell in self.totals_dict:
                                        number = [other_magic_cell, number]
                                except:
                                    pass

                            if len(number) > 1:
                                number_no = float(number[1])
                                if not (number_no * 10) % 10:
                                    number_str = str(number_no).split('.')[0]
                                else:
                                    number_str = str(number_no)
                                key = number[0]
                                if key in self.totals_dict:
                                    self.totals_dict[key][0] += number_no
                                    self.totals_dict[key][1] += 1
                                if key in ['A', 'MA', 'NA', 'KA', 'G', 'PV', 'KR', 'L', 'N', 'NS', 'M', 'MP', 'NLL', 'V',
                                           'VV', 'KT', 'KM', 'ST', 'TA', 'P']:
                                    new_cell += key
                                elif key in ['FD', 'K', 'KV', 'KVN', 'NT', 'DLS']:
                                    new_cell += number_str
                                else:
                                    new_cell += key + ' ' + number_str
                        if new_cell:
                            cell = new_cell
                    except:
                        pass
                # ---
                xf_index = sheet.cell_xf_index(r, c)
                cell_style = style_style[xf_index]
                gray = False
                multi_color = False
                if c in self.holiday_cols:
                    gray_cell_style = copy.deepcopy(cell_style)
                    pattern = xlwt.Pattern()
                    pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                    pattern.pattern_fore_colour = xlwt.Style.colour_map['tan']
                    gray_cell_style.pattern = pattern
                    sheet2.write(r + self.margin, c, cell, gray_cell_style)
                    gray = True
                elif c in self.weekend_cols:
                    gray_cell_style = copy.deepcopy(cell_style)
                    pattern = xlwt.Pattern()
                    pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                    pattern.pattern_fore_colour = xlwt.Style.colour_map['gray25']
                    gray_cell_style.pattern = pattern
                    sheet2.write(r + self.margin, c, cell, gray_cell_style)
                    gray = True
                if c <= 38:
                    color = False
                    if cell == 'A':
                        color = xlwt.Style.colour_map['light_yellow']
                    elif cell == 'K':
                        color = xlwt.Style.colour_map['light_green']
                    elif cell == 'L':
                        color = xlwt.Style.colour_map['light_blue']
                    elif cell == 'NA':
                        color = xlwt.Style.colour_map['brown']
                    elif cell == 'KR':
                        color = xlwt.Style.colour_map['light_orange']
                    elif cell == 'MA':
                        color = xlwt.Style.colour_map['sea_green']
                    if color:
                        multi_color = True
                        cell_style = copy.deepcopy(cell_style)
                        pattern = xlwt.Pattern()
                        pattern.pattern = xlwt.Pattern.SOLID_PATTERN
                        pattern.pattern_fore_colour = color
                        cell_style.pattern = pattern
                if gray and not multi_color:
                    continue
                cell = unicode(cell)
                sheet2.write(r + self.margin, c, cell, cell_style)
        self.margin += 3
        self.lines += 1

    def add_bottom(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\excel\\bottom.xls'
        else:
            xls_flocation = '/static/src/excel/bottom.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        sheet = rb.sheet_by_index(self.sheet_no)
        excel = self.wb
        sheet2 = excel.get_sheet(0)
        style_wb, style_style = copy2(rb)
        style = xlwt.XFStyle()
        style.alignment.wrap = 0
        end_col = 48 - int(self.sheet_no)
        for r in xrange(sheet.nrows):
            for c in xrange(sheet.ncols):
                if c > end_col:
                    continue
                if r == 0 and -1 >= (c - end_col - 1) >= -12:
                    cell = self.totals[c - end_col - 1]
                else:
                    cell = sheet.cell_value(r, c)
                xf_index = sheet.cell_xf_index(r, c)
                cell_style = style_style[xf_index]
                if r == 0:
                    cell_style.alignment.wrap = 0
                sheet2.write(r + self.margin, c, cell, cell_style)
        for key, value in self.totals_dict.items():
            if value and value[0] <= 0:
                continue
            row_index = self.margin + 2
            col_index = 5 + self.dict_sort.index(key) + 1
            setOutCell(sheet2, col_index, row_index, value[1])
            setOutCell(sheet2, col_index, row_index + 1, value[0])
        # Write company data
        vadovas = self.object.company_id.vadovas  # context date set in excel init
        vadovo_pareigos = vadovas.job_id.name
        asmuo = self.object.env.user
        if asmuo.employee_ids:
            asmens_pareigos = asmuo.employee_ids[0].job_id.name
        else:
            asmens_pareigos = ''
        setOutCell(sheet2, 3, self.margin + 7, vadovo_pareigos or '')
        setOutCell(sheet2, 23, self.margin + 7, vadovas.name or '')
        setOutCell(sheet2, 3, self.margin + 10, asmens_pareigos or '')
        setOutCell(sheet2, 3, self.margin + 13, asmuo.name or '')
        setOutCell(sheet2, 3, self.margin + 14, datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        self.margin += 15
        return True

    def export(self):
        self.add_bottom()
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')


class ZiniarastisPeriod(models.Model):
    _inherit = 'ziniarastis.period'

    @api.multi
    def export_excel_multiple(self):
        view_id = self.env.ref('l10n_lt_payroll.ziniarastis_period_selected_export_view_form').id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'ziniarastis.period.selected.export',
            'view_id': view_id,
            'views': [[view_id, 'form']],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_ziniarastis_period_id': self.id},
        }

    @api.multi
    def export_excel(self, department_id=False):
        self.ensure_one()
        date_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        holidays = []
        weekends = []
        while date_from_dt <= date_dt:
            is_holidays = self.env['sistema.iseigines'].search(
                [('date', '=', date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]) and True or False
            work_day = 1 if date_from_dt.weekday() not in (5, 6) and not is_holidays else 0
            if is_holidays:
                holidays.append(date_from_dt.day)
            elif not work_day:
                weekends.append(date_from_dt.day)
            date_from_dt += timedelta(days=1)
        excel = ZiniarastisExcel(self.with_context(date=self.date_to), date_dt, holidays=holidays, weekends=weekends)
        total_days = (date_dt + relativedelta(day=31)).day
        total_cols = 6 + total_days + 12 + 1
        index = 1
        related_ziniarasciai_lines = self.with_context(lang='lt_LT').related_ziniarasciai_lines
        if self._context.get('employee_ids'):
            related_ziniarasciai_lines = related_ziniarasciai_lines.filtered(lambda r: r.employee_id in self._context.get('employee_ids'))
        if department_id and type(department_id) in [int, float, long]:
            contracts_in_department = self.env['hr.contract.appointment'].sudo().search([
                '&',
                '|',
                ('department_id', '=', department_id),
                '&',
                ('employee_id.department_id', '=', department_id),
                ('department_id', '=', False),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ]).mapped('contract_id')
            related_ziniarasciai_lines = related_ziniarasciai_lines.filtered(lambda x: x.contract_id.id
                                                                                       in contracts_in_department.ids)
        for zline in related_ziniarasciai_lines.sorted(lambda r: r.employee_id.tabelio_numeris):
            line = [
                ['' for i in xrange(total_cols)],
                ['' for i in xrange(total_cols)],
                ['' for i in xrange(total_cols)],
            ]
            # Col group #1
            line[0][0] = index
            line[0][1] = zline.employee_id.tabelio_numeris
            line[0][2] = zline.employee_id.name or ''
            line[0][3] = zline.employee_id.job_id.name or ''
            line[0][4] = ','.join(map(unicode,
                                      zline.contract_id.active_appointments(self.date_from, self.date_to).mapped(
                                          'schedule_template_id.id')))
            line[0][5] = zline.num_regular_work_hours

            # Col group #2
            col_index = 5
            neatvykimai = {}
            empty_line = ['' for i in xrange(total_cols)]
            for day in zline.ziniarastis_day_ids:
                col_index += 1
                if not day.contract_id:
                    line[0][col_index] = '-'
                    continue
                if day.holiday:
                    empty_line[col_index] = 'S'
                elif datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday() in [5, 6]:
                    empty_line[col_index] = 'P'
                if day.business_trip:
                    line[2][col_index] += 'K'
                if day.business_trip and all([mark.worked_time_hours == mark.worked_time_minutes == 0
                                              for mark in day.ziniarastis_day_lines]):
                    line[0][col_index] += '0'
                if all(mark.worked_time_hours == mark.worked_time_minutes == 0 and
                       mark.tabelio_zymejimas_id.code not in NEATVYKIMAI_BE_K
                       for mark in day.ziniarastis_day_lines):
                    empty_line[col_index] = 'P'
                for mark in day.ziniarastis_day_lines:
                    code = mark.tabelio_zymejimas_id.code
                    minutes = mark.worked_time_hours * 60 + mark.worked_time_minutes
                    time_hours = float(minutes) / 60.0  # P3:DivOK
                    time_hours_rounded = tools.float_round(time_hours, precision_digits=2)
                    if tools.float_is_zero(time_hours_rounded, precision_digits=2) and code not in NEATVYKIMAI_BE_K:
                        continue
                    if code in NEATVYKIMAI_BE_K:
                        if code not in neatvykimai:
                            neatvykimai[code] = [0, 0]
                        neatvykimai[code][0] += 1
                        neatvykimai[code][1] += time_hours_rounded
                    time_value = str(time_hours_rounded)
                    value = unicode(code) + ' ' + time_value
                    if code in ['ST', 'PN', 'PK', 'KS']:
                        if line[1][col_index]:
                            line[1][col_index] += ', '
                        line[1][col_index] += value
                    elif code in ['BN', u'BĮ', 'ID', 'MD', 'K', u'SŽ', 'PR']:
                        line[2][col_index] += value
                    elif code == 'FD' and day.business_trip:
                        line[0][col_index] += 'K ' + time_value
                    elif code in ['KV', 'KVN']:
                        line[0][col_index] += time_value
                        line[2][col_index] += code
                    else:
                        line[0][col_index] += value

            # Col group #3
            col_index += 1
            line[0][col_index] = zline.days_total or ''
            line[1][col_index] = ''
            line[2][col_index] = ''

            line[0][col_index + 1] = zline.hours_worked or ''
            line[1][col_index + 1] = ''
            line[2][col_index + 1] = ''

            line[0][col_index + 2] = zline.hours_night or ''
            line[1][col_index + 2] = ''
            line[2][col_index + 2] = ''

            line[0][col_index + 3] = zline.hours_overtime or ''
            line[1][col_index + 3] = ''
            line[2][col_index + 3] = ''

            line[0][col_index + 4] = ''
            line[1][col_index + 4] = zline.hours_not_regular or ''
            line[2][col_index + 4] = ''

            line[0][col_index + 5] = ''
            line[1][col_index + 5] = ''
            line[2][col_index + 5] = zline.hours_watch_home or ''

            line[0][col_index + 6] = ''
            line[1][col_index + 6] = ''
            line[2][col_index + 6] = zline.hours_watch_work or ''

            line[0][col_index + 7] = zline.hours_weekends or ''
            line[1][col_index + 7] = ''
            line[2][col_index + 7] = ''

            line[0][col_index + 8] = zline.hours_holidays or ''
            line[1][col_index + 8] = ''
            line[2][col_index + 8] = ''

            line[0][col_index + 9] = ''
            line[1][col_index + 9] = ''
            line[2][col_index + 9] = ''

            line[0][col_index + 10] = ''
            line[1][col_index + 10] = ''
            line[2][col_index + 10] = ''

            line[0][col_index + 11] = ''
            line[1][col_index + 11] = ''
            line[2][col_index + 11] = ''

            row_index = 0
            for key, val in neatvykimai.items():
                if row_index > 2:
                    row_index = 2
                    line[row_index][col_index + 9] += '\n'
                    line[row_index][col_index + 10] += '\n'
                    line[row_index][col_index + 11] += '\n'
                line[row_index][col_index + 9] += unicode(key)
                if not (val[0] * 10) % 10:
                    val1 = unicode(val[0]).split(u'.')[0]
                else:
                    val1 = unicode(val[0])
                if not (val[1] * 10) % 10:
                    val2 = unicode(val[1]).split(u'.')[0]
                else:
                    val2 = unicode(val[1])
                line[row_index][col_index + 10] += val1
                line[row_index][col_index + 11] += val2
                row_index += 1

            for k, v in enumerate(line[0]):
                if not v:
                    line[0][k] = empty_line[k]

            excel.write_line(line)

            index += 1
        base64_file = excel.export()
        dt_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        year, month = dt_from.year, dt_from.month
        company = self.env.user.company_id.name
        filename = 'Žiniaraštis %s-%s (%s).xls' % (str(year), str(month), str(company))
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'ziniarastis.period',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        if self._context.get('archive', False):
            return base64_file
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=ziniarastis.period&res_id=%s&attach_id=%s' % (self.id, attach_id.id),
            'target': 'self',
        }


ZiniarastisPeriod()


class ExportWizard(models.TransientModel):
    _name = 'ziniarastis.export.wizard'

    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Metai',
                            default=lambda self: datetime.utcnow().year,
                            required=True)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Mėnuo', required=True,
                             default=(datetime.utcnow().month - 1))
    department_id = fields.Many2one('hr.department', string='Padalinys', required=False)

    @api.multi
    def export(self):
        self.ensure_one()
        date = datetime(self.year, self.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        period_id = self.env['ziniarastis.period'].search([('date_from', '=', date)], limit=1)
        if period_id:
            return period_id.export_excel(department_id=self.department_id.id)
        else:
            raise exceptions.Warning(_('Nurodytam periodui žiniaraštis nesuformuotas.'))


ExportWizard()


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
