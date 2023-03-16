# -*- coding: utf-8 -*-
from __future__ import division
import StringIO
import cStringIO as StringIO
import datetime
import logging
import math
import os
from collections import OrderedDict
from datetime import datetime
from sys import platform

import xlrd
import xlwt
from dateutil.relativedelta import relativedelta
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES
from xlutils.filter import XLRDReader, XLWTWriter, process
from six import iteritems

from odoo import api, exceptions, models, tools
from odoo.tools.translate import _

ezxf = xlwt.easyxf

_logger = logging.getLogger(__name__)

kwd_mark = object()
cache_styles = {}

CODES_ABSENCE = ['D', 'ID', 'KM', 'KT', 'L', 'NN', 'NP', 'NS', 'PB', 'PK', 'PN', 'ST', 'VV']
CODES_SHOWN_IN_EXPORT = PAYROLL_CODES['WATCH_HOME'] + PAYROLL_CODES['EXTRA'] + PAYROLL_CODES['OVERTIME'] + \
                        PAYROLL_CODES['DOWNTIME'] + PAYROLL_CODES['OTHER_PAID'] + PAYROLL_CODES['OTHER_SPECIAL'] + \
                        PAYROLL_CODES['UNPAID_OUT_OF_OFFICE'] + PAYROLL_CODES['OUT_OF_OFFICE']

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
        return 255
    else:
        return int(255 * (math.ceil(len(str) / float(num))))  # P3:DivOK


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
    key = (string,) + (kwd_mark,)  # + tuple(sorted(kwargs.items()))
    return cache_styles.setdefault(key, style)


def get_style(inSheet, outStyle, i, j):
    xf_index = inSheet.cell_xf_index(i, j)
    return outStyle[xf_index]


class WorkScheduleExcel:
    def __init__(self):
        self.margin = 0
        self.wb = False
        self.lines = 0
        self.sheet_no = 0
        self.day_col_width = 0
        self.first_loop = True
        self.line_template = False
        self.page_amount = 1
        self.lines_that_fit_on_page = 30.0
        self.header_month = False
        self.header_week_days = False
        self.header_holiday_days = False

    def load_top(self, month, week_days, holiday_days=[], estimated_next_employee_line_count=0):
        if not month or not week_days:
            raise exceptions.UserError("Nenumatyta sistemos klaida")

        if platform == 'win32':
            xls_flocation = '\\static\\src\\xls\\Header.xls'
        else:
            xls_flocation = '/static/src/xls/Header.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)

        self.header_month = month
        self.header_week_days = week_days
        self.header_holiday_days = holiday_days

        # Page Settings
        if (self.first_loop):
            base_sheet = wb.get_sheet(0)
            base_sheet.set_portrait(False)
            base_sheet.paper_size_code = 9
            base_sheet.print_scaling = 100
            base_sheet.horz_page_breaks = []
            self.wb = wb
            self.first_loop = False
            self.load_line()
        else:
            current_sheet = rb.sheet_by_index(self.sheet_no)
            excel = self.wb
            base_sheet = excel.get_sheet(0)
            first_r_index = self.margin

            base_sheet.merge(first_r_index, first_r_index, 0, 8)  # Merge Month Title
            base_sheet.merge(first_r_index + 1, first_r_index + 2, 0, 0)  # Merge Employee Title
            base_sheet.merge(first_r_index + 1, first_r_index + 2, 1, 1)  # Merge Department Title

            for r in xrange(current_sheet.nrows):
                for c in xrange(current_sheet.ncols):
                    cell = current_sheet.cell_value(r, c)
                    xf_index = current_sheet.cell_xf_index(r, c)
                    style = wstyle[xf_index]
                    base_sheet.write(r + self.margin, c, cell, style)

        xf_index = rb.sheet_by_index(self.sheet_no).cell_xf_index(1, 8)
        holiday_cell_style = wstyle[xf_index]

        if not self.will_fit_on_page(3 + estimated_next_employee_line_count):
            self.ensure_fits_on_page(3 + estimated_next_employee_line_count)

        if len(month) != 1:
            month_string = self.get_month_string_from_number(month[0]) + " / " + self.get_month_string_from_number(
                month[1])
        else:
            month_string = self.get_month_string_from_number(month[0]) or ''
        setOutCell(base_sheet, 0, self.margin, month_string)

        for day in range(0, len(week_days)):
            if week_days[day] in holiday_days:
                base_sheet.write(self.margin + 1, day + 2,
                                 unicode(week_days[day] or ''),
                                 holiday_cell_style)

                cell = rb.sheet_by_index(self.sheet_no).cell_value(2, day + 2)
                base_sheet.write(self.margin + 2, day + 2,
                                 cell,
                                 holiday_cell_style)
            else:
                setOutCell(base_sheet, day + 2, self.margin + 1, week_days[day] or '')

        self.margin += 3

    def load_line(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\xls\\Line.xls'
        else:
            xls_flocation = '/static/src/xls/Line.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        self.line_template = rb

    def write_employee_lines(self, employee_name, department_days):
        if not employee_name or not department_days:
            raise exceptions.UserError("Nenumatyta sistemos klaida")
        new_sheet = self.line_template.sheet_by_index(self.sheet_no)
        base_sheet = self.wb.get_sheet(0)
        sched_cell_style = ezxf(
            'font: height 140; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')

        row_height = base_sheet.row(self.margin).height

        department_line_max = {}
        employee_title_merge = 0
        for department in department_days:
            department_line_max[department] = 0
            for day in department_days[department]:
                day_length = len(department_days[department][day])
                if day_length > department_line_max[department]:
                    department_line_max[department] = day_length
            employee_title_merge += department_line_max[department]

        if not self.will_fit_on_page(employee_title_merge):
            self.ensure_fits_on_page(employee_title_merge)
            self.load_top(self.header_month, self.header_week_days, self.header_holiday_days)

        department_line_max = {}
        employee_title_merge = 0
        department_margin = 0
        for department in department_days:
            department_line_max[department] = 0
            for day in department_days[department]:
                day_length = len(department_days[department][day])
                if day_length > department_line_max[department]:
                    department_line_max[department] = day_length
            employee_title_merge += department_line_max[department]
            base_sheet.merge(self.margin + department_margin,
                             self.margin + department_margin + department_line_max[department] - 1, 1,
                             1)  # Merge Department title
            for i in range(0, 9):
                for j in range(0, department_line_max[department]):
                    # if i > 1:
                    #     if len(department_days[department][i-2]) == 1 and department_line_max[department] != 1:
                    #         base_sheet.merge(self.margin + department_margin,
                    #                          self.margin + department_margin + department_line_max[department] - 1, i,
                    #                          i)  # Merge Single cells
                    if i > 1:
                        base_sheet.merge(self.margin + department_margin,
                                         self.margin + department_margin + department_line_max[department] - 1, i,
                                         i)  # Merge cells to department height
                    base_sheet.write(self.margin + department_margin + j, i,
                                     unicode(''),
                                     sched_cell_style)

            day_index = 0
            for day in department_days[department]:
                line_index = 0
                line_string = ""
                for line in department_days[department][day]:
                    line_string += unicode(department_days[department][day][line] or '')
                    if line_index != department_line_max[department] - 1 and len(department_days[department][day]) != 1:
                        line_string += "\n"
                    line_index += 1
                base_sheet.write(self.margin + department_margin, day_index + 2,
                                 unicode(line_string or ''),
                                 sched_cell_style)
                day_index += 1

            base_sheet.write(self.margin + department_margin, 1, unicode(department or ''), sched_cell_style)
            if row_height < getRowHeightNeeded(department or '', 14) and department_line_max[department] == 1:
                row_height = getRowHeightNeeded(department or '', 14)
            department_margin += department_line_max[department]

        base_sheet.merge(self.margin, self.margin + employee_title_merge - 1, 0, 0)  # Merge Employee Name
        for i in range(0, employee_title_merge):
            base_sheet.write(self.margin + i, 0, '', sched_cell_style)
        base_sheet.write(self.margin, 0, unicode(employee_name or ''), sched_cell_style)
        if row_height < getRowHeightNeeded(unicode(employee_name or ''), 14) and len(department_days) == 1 and \
                department_line_max[next(iter(department_days))] == 1:
            row_height = getRowHeightNeeded(unicode(employee_name or ''), 14)

        base_sheet.row(self.margin).height = row_height

        self.margin += employee_title_merge
        self.lines += 1

    def get_month_string_from_number(self, month):
        months = {
            1: "Sausis",
            2: "Vasaris",
            3: "Kovas",
            4: "Balandis",
            5: "Gegužė",
            6: "Birželis",
            7: "Liepa",
            8: "Rugpjūtis",
            9: "Rugsėjis",
            10: "Spalis",
            11: "Lapkritis",
            12: "Gruodis"
        }
        return unicode(months.get(month, "SISTEMOS KLAIDA NUSTATANT MĖNESĮ"))

    def ensure_fits_on_page(self, margin_to_be_added):
        # P3:DivOK
        if (self.margin + margin_to_be_added) / self.lines_that_fit_on_page > self.page_amount:
            self.page_amount += 1
            self.wb.get_sheet(self.sheet_no).horz_page_breaks.append((self.margin, 0, 0))

    def will_fit_on_page(self, margin_to_be_added):
        # P3:DivOK
        if (self.margin + margin_to_be_added) / self.lines_that_fit_on_page > self.page_amount:
            return False
        else:
            return True

    def export(self):
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')


class WorkScheduleDay(models.Model):
    _inherit = "work.schedule.day"

    @api.multi
    def export_excel(self, data):
        view_type = data.get('export_view_type', False)
        if view_type == 'month_view':
            return self.export_month_view()
        dates = self.mapped('date')
        month_start_date = min(dates)
        month_end_date = max(dates)
        excel = WorkScheduleExcel()

        if len(set(self.mapped('work_schedule_line_id.year'))) > 1 or len(set(self.mapped('work_schedule_line_id.month'))) > 1:
            raise exceptions.UserError(_('Grafiko eksportavimas leidžiamas tik vienam periodui'))

        year = self.mapped('work_schedule_line_id.year')[0]
        month = self.mapped('work_schedule_line_id.month')[0]

        period_start = datetime(year, month, 1)
        period_end = period_start+relativedelta(day=31)
        month_start_weekday = period_start.weekday()
        month_end_weekday = period_end.weekday()

        days_to_get_start = (period_start - relativedelta(days=month_start_weekday)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        days_to_get_end = (period_end + relativedelta(days=abs(month_end_weekday - 6))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        schedule_month = month

        employee_ids = self.mapped('employee_id.id')
        department_ids = self.mapped('department_id.id')
        days_to_export_ids = self.env['work.schedule.day'].search([('employee_id', 'in', employee_ids),
                                                                 ('department_id', 'in', department_ids),
                                                                 ('date', '>=', days_to_get_start),
                                                                 ('date', '<=', days_to_get_end),
                                                                   ('work_schedule_id', 'in', self.mapped('work_schedule_id.id'))
                                                                 ])

        break_users_separate_tables = data['break_users_separate_tables']
        break_users_separate_pages = data['break_users_separate_pages']
        show_other_month_days = data['show_other_month_days']

        if not break_users_separate_tables:
            break_users_separate_pages = False

        free_days = self.env['sistema.iseigines'].search([('date', '>=', days_to_get_start), ('date', '<=', days_to_get_end)]).mapped('date')

        day = days_to_get_start
        weekday = week = 0
        week_headers = {}
        week_free_days = {}
        while day <= days_to_get_end:
            if weekday == 7:
                weekday = 0
            if weekday == 0:
                week_free_days[week] = list()
                current_date = datetime.strptime(day, tools.DEFAULT_SERVER_DATE_FORMAT)
                month = current_date.month
                days = list()
                for i in range(0, 7):
                    temp_date = current_date + relativedelta(days=i)
                    days.append(temp_date.day)
                    if temp_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT) in free_days:
                        week_free_days[week].append(temp_date.day)
                week_headers[week] = {}
                if current_date.month != (current_date + relativedelta(days=6)).month:
                    week_headers[week]['month'] = [current_date.month, (current_date + relativedelta(days=6)).month]
                else:
                    week_headers[week]['month'] = [month]
                week_headers[week]['days'] = days
                week += 1
            weekday += 1
            day = (datetime.strptime(day, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)

        for i in range(0, week):
            if not break_users_separate_tables:
                excel.load_top(week_headers[i]['month'], week_headers[i]['days'], week_free_days[i], 3)
            for empl in employee_ids:
                if break_users_separate_tables:
                    max_lines = 0
                    for day in range(0, 7):
                        day_date = (datetime.strptime(days_to_get_start,
                                                      tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                            days=(day + i * 7))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        day_date_day_ids = days_to_export_ids.filtered(
                            lambda d: d['employee_id']['id'] == empl and d['date'] == day_date)
                        if max_lines < len(day_date_day_ids.mapped('line_ids')):
                            max_lines = len(day_date_day_ids.mapped('line_ids'))
                    excel.load_top(week_headers[i]['month'], week_headers[i]['days'], week_free_days[i], max_lines)
                employee = days_to_export_ids.filtered(lambda d: d['employee_id']['id'] == empl)[0].employee_id
                employee_name = employee.name
                employee_data_to_export = {}
                line_max = 0
                for department in days_to_export_ids.filtered(lambda d: d['employee_id']['id'] == empl).mapped(
                        'department_id'):
                    employee_data_to_export[department.name] = {}
                    for day in range(0, 7):
                        employee_data_to_export[department.name][day] = {}
                        day_date = (datetime.strptime(days_to_get_start,
                                                      tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                            days=(day + i * 7))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        day_month = (datetime.strptime(days_to_get_start,
                                                       tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                            days=(day + i * 7))).month
                        if day_month == schedule_month or day_month != schedule_month and show_other_month_days:
                            line_ids = days_to_export_ids.filtered(
                                lambda d: d['date'] == day_date and d['department_id']['id'] == department.id and
                                          d['employee_id']['id'] == empl).mapped('line_ids')
                            if len(line_ids) > line_max:
                                line_max = len(line_ids)
                            for j in range(0, len(line_ids)):
                                employee_data_to_export[department.name][day][j] = line_ids.sorted('name')[j].name
                            if len(line_ids) == 0:
                                employee_data_to_export[department.name][day][0] = '-'
                        else:
                            employee_data_to_export[department.name][day][0] = '-'
                            if 1 > line_max:
                                line_max = 1

                excel.write_employee_lines(employee_name, employee_data_to_export)
                if break_users_separate_tables:
                    excel.margin += 2
                if break_users_separate_pages:
                    excel.wb.get_sheet(0).horz_page_breaks.append((excel.margin, 0, 0))
                    excel.page_amount += 1
            excel.margin += 2

        base64_file = excel.export()
        filename = 'Darbo_Grafikas_(' + month_start_date + '_' + month_end_date + ').xls'
        attach_id = self.env['ir.attachment'].sudo().create({
            'res_model': 'work.schedule.day',
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
            'url': '/web/binary/download?res_model=work.schedule.day&res_id=%s&attach_id=%s' % (self[0].id, attach_id.id),
            'target': 'self',
        }

    @api.model
    def get_export_class(self):
        return WorkScheduleMonthlyExcel()

    @api.multi
    def export_month_view(self):
        dates = self.mapped('date')
        department = self.mapped('department_id.display_name')[0] if len(self.mapped('department_id.display_name')) == 1 else False
        month_start_date = min(dates)
        month_end_date = max(dates)
        excel = self.get_export_class()

        holidays = self.env['sistema.iseigines'].search([('date', '<=', month_end_date), ('date', '>=', month_start_date)])
        holiday_days = []
        for holiday in holidays:
            holiday_days.append(datetime.strptime(holiday.date, tools.DEFAULT_SERVER_DATE_FORMAT).day)
        weekends = []
        for date in dates:
            dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if dt.weekday() in [5, 6]:
                weekends.append(dt.day)
        month = datetime.strptime(month_start_date, tools.DEFAULT_SERVER_DATE_FORMAT).month
        year = datetime.strptime(month_start_date, tools.DEFAULT_SERVER_DATE_FORMAT).year
        excel.create_document(year=year, month=month, num_days=len(set(dates)), holiday_days=holiday_days, weekends=weekends, company_id=self.env.user.company_id, department=department)

        employee_ids = self.mapped('employee_id.id')
        department_ids = self.mapped('department_id.id')
        domain = [('employee_id', 'in', employee_ids),
                 ('department_id', 'in', department_ids),
                 ('date', '>=', month_start_date),
                 ('date', '<=', month_end_date),
                  ('work_schedule_id', 'in', self.mapped('work_schedule_id.id'))
                 ]

        days = self.env['work.schedule.day'].search(domain)

        domain = [('employee_id','in',employee_ids),
                   ('date_start','<=',month_end_date),
                   '|',
                   ('date_end','=',False),
                   ('date_end','>=',month_start_date),]

        appointments = self.sudo().env['hr.contract.appointment'].search(domain)
        public_holidays = self.env['sistema.iseigines'].search([
            ('date','<=',max(days.mapped('date'))),
            ('date','>=',min(days.mapped('date')))
        ]).mapped('date')
        data = {}
        employees = days.mapped('employee_id')
        for employee in employees.sorted(lambda r: r.name):
            empl_days = days.filtered(lambda r: r['employee_id']['id'] == employee.id)
            empl_departments = empl_days.mapped('department_id').sorted('display_name')
            if len(empl_departments) == 0:
                continue
            employee_data = {}
            employee_data['etatas'] = '-'
            employee_data['h_per_day'] = '-'
            empl_appointments = appointments.filtered(lambda r: r['employee_id']['id'] == employee.id).sorted('date_start', reverse=True)
            if empl_appointments:
                appointment = empl_appointments[0]
                etatas = appointment.schedule_template_id.etatas
                employee_data['etatas'] = round(etatas,2)
                employee_data['h_per_day'] = round(appointment.schedule_template_id.avg_hours_per_day,2)
            employee_data['departments'] = {}
            for department in empl_departments:
                department_vals = {}
                department_days = empl_days.filtered(lambda r: r['department_id']['id'] == department.id).sorted('date')
                for day in department_days:
                    day_vals = []
                    day_holidays = day.schedule_holiday_id
                    day_appointment = empl_appointments.filtered(
                        lambda a: a.date_start <= day.date and (not a.date_end or a.date_end >= day.date))
                    lines = day.line_ids.sorted('name')
                    no_work_time_set = tools.float_is_zero(sum(lines.mapped('worked_time_total')), precision_digits=2)
                    day_weekday = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday()
                    is_weekend = day_weekday in [5, 6]
                    is_public_holiday = day.date in public_holidays
                    if day_holidays:
                        day_vals.append({
                            'time_from': '',
                            'time_to': '',
                            'holiday_code': day_holidays.holiday_status_id.tabelio_zymejimas_id.code,
                            'total': 0.0
                        })
                    elif (is_weekend or is_public_holiday) and (not lines or no_work_time_set or (len(lines) == 1 and lines.name == '-' and day_appointment)):
                        special_code = 'S' if day.date in public_holidays else 'P'
                        day_vals.append({
                            'time_from': '',
                            'time_to': '',
                            'holiday_code': special_code,
                            'total': 0.0
                        })
                    elif not lines:
                        day_vals.append({
                            'time_from': '',
                            'time_to': '',
                            'holiday_code': 'P',
                            'total': 0.0
                        })
                    else:
                        for line in lines:
                            line_vals = {}
                            code = line.tabelio_zymejimas_id.code if not day.free_day else 'P'
                            if (line.tabelio_zymejimas_id.is_holidays and code not in CODES_ABSENCE) or code == 'L' or day.free_day:
                                line_vals['time_from'] = ''
                                line_vals['time_to'] = ''
                                line_vals['holiday_code'] = code
                                line_vals['total'] = 0.0
                            else:
                                if not tools.float_is_zero(line.worked_time_total, precision_digits=2):
                                    time_from = '{0:02.0f}:{1:02.0f}'.format(*divmod(line.time_from * 60, 60))
                                    time_to = '{0:02.0f}:{1:02.0f}'.format(*divmod(line.time_to * 60, 60))
                                else:
                                    time_from = ''
                                    time_to = ''
                                line_vals['time_from'] = time_from
                                line_vals['time_to'] = time_to
                                line_vals['holiday_code'] = False
                                line_vals['work_code'] = code if code in CODES_SHOWN_IN_EXPORT else False
                                line_vals['total'] = line.time_to - line.time_from
                            day_vals.append(line_vals)
                    day = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT).day
                    department_vals[day] = day_vals
                employee_data['departments'][department.name] = department_vals
            data[(employee.name, employee.job_id.name)] = employee_data

        user_employee = self.env.user.employee_ids[0] if self.env.user.employee_ids else False
        if not self.env.user.has_group('work_schedule.group_schedule_manager'):
            user_employee = False
        user_name = user_employee.name_related if user_employee else False
        user_job_name = user_employee.job_id.display_name if user_employee else False
        excel.populate(data, user_name, user_job_name)

        base64_file = excel.export()
        filename = 'Darbo_Grafikas_(' + month_start_date + '_' + month_end_date + ').xls'
        attach_id = self.env['ir.attachment'].sudo().create({
            'res_model': 'work.schedule.day',
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
            'url': '/web/binary/download?res_model=work.schedule.day&res_id=%s&attach_id=%s' % (self[0].id, attach_id.id),
            'target': 'self',
        }


WorkScheduleDay()

class WorkScheduleMonthlyExcel:
    def __init__(self):
        self.wb = False
        self.pages = 0
        self.page_row = 0
        self.page_col = -1
        self.num_days = 0
        self.max_employee_rows_per_page = 32
        self.top = 0
        self.month = 0
        self.year = datetime.utcnow().year
        self.company_id = False
        self.holiday_days = []
        self.weekends = []
        self.day_width = 800
        self.default_width = 256 * 10
        self.totals_width = 700
        self.page_width = 36500 #THIS IS THE STANDART A4 PAGE LANDSCAPE WIDTH CALCULATED USING WHO THE HELL KNOWS WHAT METHOD IN "WHAT IS THIS" MEASURMENT UNITS (INCLUDING 0.3" PRINTING MARGINS) DON'T CHANGE UNLESS PAGE WILL HAVE DIFFERENT MARGINS

        self.style_header_regular = ezxf('font: height 150; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_header_regular_rotated = ezxf('font: height 120; align: rotation -90, wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_header_day_regular = ezxf('font: height 120; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_header_day_holiday = ezxf('pattern: pattern solid, fore_color coral; font: height 120; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_header_day_weekend = ezxf('pattern: pattern solid, fore_color ice_blue; font: height 120; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_regular = ezxf('font: height 120; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_regular = ezxf('font: height 100; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_weekend = ezxf('pattern: pattern solid, fore_color ice_blue; font: height 100; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_holiday = ezxf('pattern: pattern solid, fore_color coral; font: height 100; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_regular_bold = ezxf(
            'font: height 100, bold on; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_weekend_bold = ezxf(
            'font: bold on; pattern: pattern solid, fore_color ice_blue; font: height 100; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_main_day_holiday_bold = ezxf(
            'font: bold on; pattern: pattern solid, fore_color coral; font: height 100; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        self.style_for_cell_merging = ezxf(
            'borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')

    def create_document(self, year, month, num_days=0, holiday_days=[], weekends=[], company_id=False, department=False):
        book = xlwt.Workbook()
        sheet = book.add_sheet("Grafikas", cell_overwrite_ok=True)
        sheet.set_portrait(False)
        sheet.paper_size_code = 9
        sheet.print_scaling = 100
        self.num_days = num_days
        self.holiday_days = holiday_days
        self.weekends = weekends
        self.year = year
        self.department_name = department
        self.month = self.get_month_string_from_number(month)
        self.company_id = company_id
        self.wb = book

    def page_width_left(self):
        col_width = 0
        sheet = self.wb.get_sheet(0)
        for i in range(0+self.additional_cols(), 5+self.num_days+2+self.additional_cols()):
            col_width += sheet.col(i).width
        return (self.page_width - col_width)

    def additional_cols(self):
        additional_cols = (self.page_col) * (5 + self.num_days + 3)
        return additional_cols

    def additional_rows(self):
        additional_rows = (self.page_row) * (self.max_employee_rows_per_page + 8)
        return additional_rows

    def merge_cells(self, row_start, row_end, col_start, col_end, borders=True, header_company_info=False):
        sheet = self.wb.get_sheet(0)
        add = 0 if header_company_info else 1
        if borders:
            sheet.merge(row_start + self.additional_rows() + add, row_end + self.additional_rows() + add,
                        col_start + self.additional_cols(), col_end + self.additional_cols(), self.style_for_cell_merging)
        else:
            sheet.merge(row_start + self.additional_rows() + add, row_end + self.additional_rows() + add,
                        col_start + self.additional_cols(), col_end + self.additional_cols())

    def write_header_cell(self, row, column, data, rotated=False, header_company_info=False):
        add = 0 if header_company_info else 1
        style = self.style_header_regular
        if rotated:
            style = self.style_header_regular_rotated
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, style)

    def write_schedule_cell(self, row, column, data, company_info=False, header_company_info=False, small=False, small_with_border_top=False):
        add = 0 if header_company_info else 1
        style = self.style_main_regular
        if company_info:
            style = ezxf('font: height 160; align: wrap on, vert centre, horiz left;')
        if small:
            style = ezxf('font: height 125; align: wrap on, vert centre, horiz left;')
        if small_with_border_top:
            style = ezxf('font: height 125; align: wrap on, vert centre, horiz left; borders: top thin, top_colour black;')
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, style)

    def write_header_cell_mod(self, row, column, data, company_info=False, header_company_info=False, small=False, left=False):
        add = 0 if header_company_info else 1
        style = self.style_main_regular
        if company_info:
            if left:
                style = ezxf('font: height 250, bold on; align: wrap on, vert centre, horiz left;')
            else:
                style = ezxf('font: height 250, bold on; align: wrap on, vert centre, horiz centre;')
        if small:
            if left:
                style = ezxf('font: height 200, bold on; align: wrap on, vert centre, horiz left;')
            else:
                style = ezxf('font: height 200, bold on; align: wrap on, vert centre, horiz centre;')
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, style)

    def write_header_day(self, row, column, data, header_company_info=False):
        add = 0 if header_company_info else 1
        if isinstance(data, int) and int(data) in self.holiday_days:
            style = self.style_header_day_holiday
        elif isinstance(data, int) and int(data) in self.weekends:
            style = self.style_header_day_weekend
        else:
            style = self.style_main_day_regular
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, style)

    def write_schedule_day(self, row, column, data, day=False, bold=False, header_company_info=False):
        add = 0 if header_company_info else 1
        if day and isinstance(day, int) and int(day) in self.holiday_days:
            style = self.style_main_day_holiday if not bold else self.style_main_day_holiday_bold
        elif day and isinstance(day, int) and int(day) in self.weekends:
            style = self.style_main_day_weekend if not bold else self.style_main_day_weekend_bold
        else:
            style = self.style_main_day_regular if not bold else self.style_main_day_regular_bold
        style.num_format_str = '@'
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, style)
        style.borders.top = 1
        style.borders.bottom = 1

    def set_cell_width(self, col, width):
        self.wb.get_sheet(0).col(col + self.additional_cols()).width = width

    def write_empty_footer_cell(self, row, column, left=False, header_company_info=False):
        add = 0 if header_company_info else 1
        style = ezxf('font: height 120; align: wrap on, vert centre, horiz center; borders: top thin, top_colour black;')
        if left:
            style = ezxf(
                'font: height 120; align: wrap on, vert centre, horiz center; borders: left thin, left_colour black;')
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), '', style)

    def write_regular_cell(self, row, column, data, header_company_info=False):
        add = 0 if header_company_info else 1
        self.wb.get_sheet(0).write(row + self.additional_rows() + add, column + self.additional_cols(), data, self.style_header_regular)

    def row_height(self, row, height):
        sheet = self.wb.get_sheet(0)
        sheet.row(row).height_mismatch = True
        sheet.row(row).height = 256 * height

    def create_top(self, user_name=False, user_job_name=False):
        if not self.wb:
            self.create_document()
        self.pages += 1
        self.top = 0
        self.page_col += 1
        #XLWT HAS ROW LIMIT, SO ONLY 5 PAGES CAN BE WRITTEN HORIZONTALLY
        if self.page_col > 5:
            self.page_col = 0
            self.page_row += 1

        if self.company_id:
            self.merge_cells(0, 3, 0, 4, borders=False, header_company_info=True)
            self.write_header_cell_mod(0, 0, unicode(self.company_id.display_name), company_info=True,
                                       header_company_info=True)

        self.merge_cells(0, 3, 5, self.num_days - 1, borders=False, header_company_info=True)
        self.write_header_cell_mod(0, 5,
                                   unicode('DARBO GRAFIKAS\n' + str(self.year) + ' m. ' + self.month),
                                   company_info=True, header_company_info=True)
        self.merge_cells(0, 3, self.num_days, self.num_days + 7, borders=False, header_company_info=True)
        self.write_header_cell_mod(0, self.num_days, unicode('Nr.\n\nTVIRTINU:'), company_info=True,
                                   header_company_info=True, left=True)

        # ---MERGE HEADER---
        self.merge_cells(3, 6, 0, 0)
        self.merge_cells(3, 6, 1, 1)
        self.merge_cells(3, 6, 2, 2)
        self.merge_cells(3, 6, 3, 3)
        self.merge_cells(3, 6, 4, 4)
        self.merge_cells(3, 4, 5, self.num_days + 4)
        self.merge_cells(6, 6, 5, self.num_days + 4)
        self.merge_cells(3, 3, 5 + self.num_days, 6 + self.num_days)
        self.merge_cells(4, 6, 5 + self.num_days, 5 + self.num_days)
        self.merge_cells(4, 6, 6 + self.num_days, 6 + self.num_days)

        department_name = '' if not self.department_name else self.department_name + ', '

        # ---WRITE STATIC DATA---
        self.write_header_cell(3, 0, unicode('Nr.'))
        self.write_header_cell(3, 1, unicode('Vardas, pavardė'))
        self.write_header_cell(3, 2, unicode('Padalinys') if not self.department_name else unicode('Pareigos'))
        self.write_header_cell(3, 3, unicode('Etatas'))
        self.write_header_cell(3, 4, unicode('Val. per dieną'))
        self.write_header_cell(3, 5, unicode(str(department_name + 'Dienos')))
        self.write_header_cell(3, self.num_days + 5, unicode('Viso'))
        self.write_header_cell(4, self.num_days + 5, unicode('Darbo dienų'), rotated=True)
        self.write_header_cell(4, self.num_days + 6, unicode('Darbo valandų'), rotated=True)

        # ---SET WIDTH---
        self.set_cell_width(0, self.day_width)
        self.set_cell_width(1, self.default_width)
        self.set_cell_width(2, self.default_width - 150)
        self.set_cell_width(3, self.day_width * 2)
        self.set_cell_width(4, self.day_width * 2)
        self.set_cell_width(self.num_days + 5, self.day_width)
        self.set_cell_width(self.num_days + 6, self.day_width + 150)

        for day in range(1, self.num_days + 1):
            self.write_header_day(5, 4 + day, day)
            self.set_cell_width(4 + day, self.day_width)

        # ---MERGE AND SET FINAL CELL---
        self.merge_cells(3, 6, self.num_days + 7, self.num_days + 7)
        self.write_header_cell(3, self.num_days + 7, unicode('Pastabos'), rotated=self.num_days > 30)
        self.set_cell_width(self.num_days + 7, self.page_width_left())

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 0, 2)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 0, 2)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 3, 4)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 3, 4)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 5, 9)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 5, 9)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 10, 14)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 10, 14)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 15, 19)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 15, 19)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 20, 24)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 20, 24)

        self.merge_cells(self.max_employee_rows_per_page + 1, self.max_employee_rows_per_page + 1, 25, 29)
        self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 25, 29)

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 0, unicode('Žymėjimas'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 0, unicode('Paaiškinimas'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 3, unicode('A'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 3, unicode('Kasmetinės atostogos'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 5, unicode('P'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 5, unicode('Poilsio dienos'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 10, unicode('L'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 10, unicode('Nedarbingumas dėl ligos ar traumų'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 15, unicode('K'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 15, unicode('Komandiruotė'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 20, unicode('ND'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 20,unicode('Neatvykimas į darbą administracijai leidus'))

        self.write_schedule_cell(self.max_employee_rows_per_page + 1, 25, unicode('NS'))
        self.write_schedule_cell(self.max_employee_rows_per_page + 2, 25,unicode('Nedarbingumas ligoniams slaugyti, turint pažymas'))

        for i in range(0, 30):
            self.write_empty_footer_cell(self.max_employee_rows_per_page + 4, i)

        for i in range(0, 3):
            self.write_empty_footer_cell(self.max_employee_rows_per_page + 1 + i, 30, left=True)

        self.wb.get_sheet(0).horz_page_breaks.append((self.max_employee_rows_per_page + 8 + self.additional_rows(), 0, 0))
        self.wb.get_sheet(0).vert_page_breaks.append((self.num_days + 8 + self.additional_cols(), 0, 0))

        # Company settings extra text
        extra_text = False
        show_user_text = self.company_id.show_user_who_exported_info == 'show'
        if (user_job_name or user_name) and show_user_text:
            extra_text = 'Darbo grafiką sudarė '
            if user_job_name:
                extra_text += user_job_name.lower()
                if user_name:
                    extra_text += ' - '
            if user_name:
                extra_text += user_name
        if extra_text:
            self.merge_cells(self.max_employee_rows_per_page + 2, self.max_employee_rows_per_page + 3, 31, 35,
                             borders=False, header_company_info=True)
            self.write_schedule_cell(self.max_employee_rows_per_page + 2, 31, unicode(extra_text), company_info=True, header_company_info=True, small=True)

        extra_text1 = self.company_id.schedule_export_extra_text_1
        extra_text2 = self.company_id.schedule_export_extra_text_2

        if bool(extra_text1):
            # Used to be default '''Pirma pietų pertrauka darbuotojams suteikiama praėjus ne mažiau kaip 4 valandoms nuo darbo pradžios. Dirbant 12 ar 14 valandų pamainą pagal darbo grafiką, yra suteikiamos dvi poilsio pertraukos po 30 minučių'''
            self.merge_cells(self.max_employee_rows_per_page + 6, self.max_employee_rows_per_page + 6, 0, self.num_days + 7,
                             borders=False, header_company_info=True)
            self.write_schedule_cell(self.max_employee_rows_per_page + 6, 0, unicode(extra_text1), company_info=True,
                                     header_company_info=True, small=True)

        if bool(extra_text2):
            # Used to be default '''Dirbant 24 valandų pamainą pagal darbo grafiką, yra suteikiamos 3 poilsio pertraukos po 30 minučių. Poilsio pertraukomis darbuotojas pasinaudoja savo nuožiūra bei atsižvelgdamas į darbo krūvį. Pietų pertraukų laikas yra įskaičiuotas į nurodytą darbo valandų laiką'''
            self.merge_cells(self.max_employee_rows_per_page + 7, self.max_employee_rows_per_page + 7, 0, self.num_days + 7,
                             borders=False, header_company_info=True)

            self.write_schedule_cell(self.max_employee_rows_per_page + 7, 0, unicode(extra_text2), company_info=True,
                                     header_company_info=True, small=True)

        self.top += 7

    def populate(self, data, user_name=False, user_job_name=False):
        number = 0
        page_index = 0
        write_footer = False
        for employee, employee_data in iteritems(OrderedDict(sorted(data.items(), key=lambda e: e[0]))):
            number += 1
            #First we need to find out how many lines in total this employee has
            total_lines = 0
            department_line_amount = {}
            for department, department_data in iteritems(employee_data['departments']):
                department_max_lines = 0
                for day in range(1, self.num_days + 1):
                    lines = department_data.get(day, False)
                    if not lines:
                        continue
                    if len(lines) > department_max_lines:
                        department_max_lines = len(lines)
                department_max_lines = max(department_max_lines, 1)
                department_line_amount[department] = department_max_lines * 2 + 1
                total_lines += department_line_amount[department]

            if self.pages == 0 or self.top + total_lines > self.max_employee_rows_per_page:
                if self.pages != 0:
                    for i in range(0, self.num_days + 4 + 4):
                        self.write_empty_footer_cell(self.top, i)

                self.create_top(user_name, user_job_name)
                page_index = 0
                index = 0

            if number == len(data):
                write_footer = True

            self.merge_cells(self.top, self.top + total_lines-1, 0, 0)
            self.merge_cells(self.top, self.top + total_lines-1, 1, 1)
            self.write_schedule_cell(self.top, 0, unicode(str(number)))
            job_name = employee[1] if employee[1] else ''
            self.write_schedule_cell(self.top, 1, unicode(employee[0]))

            employee_top = 0
            for department, department_data in iteritems(employee_data['departments']):
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 2,
                                 2)
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 3,
                                 3)
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 4,
                                 4)
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 4 + self.num_days + 1,
                                 4 + self.num_days + 1)
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 4 + self.num_days + 2,
                                 4 + self.num_days + 2)
                self.merge_cells(self.top + employee_top,
                                 self.top + employee_top + department_line_amount[department]-1,
                                 4 + self.num_days + 3,
                                 4 + self.num_days + 3)

                self.write_schedule_cell(self.top + employee_top, 2, unicode(department) if not self.department_name else unicode(job_name))
                self.write_schedule_cell(self.top + employee_top, 3, unicode(employee_data['etatas']))
                self.write_schedule_cell(self.top + employee_top, 4, unicode(employee_data['h_per_day']))
                self.write_schedule_cell(self.top + employee_top, 4 + self.num_days + 3, unicode(''))

                department_time_sum = 0.0
                department_day_sum = 0

                max_day_lines = 0
                for day in range(1, self.num_days + 1):
                    max_day_lines = max(max_day_lines, len(department_data.get(day, False))*2)

                for day in range(1, self.num_days + 1):
                    lines = department_data.get(day, False)
                    if not lines:
                        for x in range(0, department_line_amount[department] - 1, 2):
                            self.merge_cells(self.top + employee_top + x,
                                             self.top + employee_top + x + 1,
                                             4 + day,
                                             4 + day)

                            self.write_schedule_day(self.top + employee_top + x, 4 + day, '', day=day)
                        self.write_schedule_day(self.top + employee_top + x+2, 4 + day, '', day=day, bold=True)
                        continue
                    line_index = 0
                    line_sum = 0
                    for line in lines:
                        if line.get('holiday_code', False):
                            self.merge_cells(self.top + employee_top + line_index,
                                             self.top + employee_top + line_index + 1,
                                             4 + day,
                                             4 + day)
                            self.write_schedule_day(self.top + employee_top + line_index, 4 + day, unicode(line['holiday_code']), day=day)
                        else:
                            work_code = line.get('work_code')
                            self.merge_cells(self.top + employee_top + line_index,
                                             self.top + employee_top + line_index + 1,
                                             4 + day,
                                             4 + day)
                            cell_data = line['time_from'] + ' ' + line['time_to']
                            if work_code:
                                cell_data += ' ' + work_code
                            self.write_schedule_day(self.top + employee_top + line_index, 4 + day,
                                                    cell_data, day=day)
                            line_sum += line['total']
                        line_index += 2
                    department_time_sum += line_sum
                    department_day_sum += 1 if not tools.float_is_zero(line_sum, precision_digits=2) else 0

                    all_index = line_index
                    for i in range(line_index, department_line_amount[department]-1, 2):
                        self.merge_cells(self.top + employee_top + i,
                                         self.top + employee_top + i + 1,
                                         4 + day,
                                         4 + day)

                        self.write_schedule_day(self.top + employee_top + i, 4 + day,'', day=day)
                        all_index += 2

                    sum = '{0:02.0f}:{1:02.0f}'.format(*divmod(line_sum * 60, 60)) if not tools.float_is_zero(line_sum, precision_digits=2) else ''
                    self.write_schedule_day(self.top + employee_top + all_index, 4 + day, sum, day=day, bold=True)

                self.write_schedule_day(self.top + employee_top, 4 + self.num_days + 1, unicode(department_day_sum))
                self.write_schedule_day(self.top + employee_top, 4 + self.num_days + 2, unicode('{0:02.0f}:{1:02.0f}'.format(*divmod(round(department_time_sum, 2) * 60, 60))))

                employee_top += department_line_amount[department]

            self.top += total_lines

        if write_footer:
            for i in range(0, self.num_days + 4 + 4):
                self.write_empty_footer_cell(self.top, i)

    def get_month_string_from_number(self, month):
        months = {
            1: "Sausis",
            2: "Vasaris",
            3: "Kovas",
            4: "Balandis",
            5: "Gegužė",
            6: "Birželis",
            7: "Liepa",
            8: "Rugpjūtis",
            9: "Rugsėjis",
            10: "Spalis",
            11: "Lapkritis",
            12: "Gruodis"
        }
        return unicode(months.get(month, "SISTEMOS KLAIDA NUSTATANT MĖNESĮ"))

    def export(self):
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')
