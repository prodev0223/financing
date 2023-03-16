# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import tools, models, fields, api
from sys import platform
import xlrd
import os
import cStringIO as StringIO
from xlwt import Formula
from odoo.addons.l10n_lt_payroll.model.darbuotojai_old_api import copy2, setOutCell
from six import iteritems


class AtostoginiuKaupiniuWizard(models.TransientModel):

    _name = 'atostoginiu.kaupiniu.wizard'

    def _date(self):
        return (datetime.now() + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    date = fields.Date(string='Data', default=_date)
    threaded = fields.Boolean(compute='_compute_background_report')

    @api.multi
    @api.depends('date')
    def _compute_background_report(self):
        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        for rec in self:
            rec.threaded = threaded

    @api.multi
    def generate_pdf_report(self, force_html=False):
        """
        Generate a pdf or html report of holiday reserves of all employees according to the date of the wizard
        """
        self.ensure_one()
        date = self.date
        employees = self._find_employees_who_do_not_perform_voluntary_internships_by_date()
        reserve_info = employees.get_holiday_reserve_info(date)
        reserve_info = self.convert_reserve_employee_ids_to_names(reserve_info)
        data = {
            'date': date,
            'data': reserve_info,
        }
        report_name = 'l10n_lt_payroll.atostoginiu_kaupiniu_report_template'
        res = self.env['report'].get_action(self, report_name, data=data)
        if 'report_type' in res:
            if force_html:
                res['report_type'] = 'qweb-html'
            else:
                res['report_type'] = 'qweb-pdf'
        return res

    @api.multi
    def open_report(self):
        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            filename = 'Atostogų likučiai %s %s' % (self.env.user.company_id.name, self.date)
            report = 'Atostogų kaupinių apskaitymas'
            return self.env['robo.report.job'].generate_report(
                self, 'generate_pdf_report', report, returns='action', forced_name=filename, forced_extension='pdf')
        else:
            return self.generate_pdf_report(force_html=self._context.get('force_html'))

    @api.multi
    def _find_employees_who_do_not_perform_voluntary_internships_by_date(self):
        self.ensure_one()
        date = self.date
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            HrContract = self.sudo().env['hr.contract']
        else:
            HrContract = self.env['hr.contract']

        employees = HrContract.with_context(active_test=False).search([
            ('rusis', '!=', 'voluntary_internship'),
            ('date_start', '<=', date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date)
        ]).mapped('employee_id').filtered(lambda employee: employee.type != 'intern')
        return employees

    @api.model
    def convert_reserve_employee_ids_to_names(self, data):
        employee_list = []
        for employee_id, employee_data in iteritems(data):
            employee = self.env['hr.employee'].browse(employee_id)
            employee_data['tabelio_numeris'] = employee.tabelio_numeris
            employee_data['employee_name'] = employee.name
            employee_list.append(employee_data)
        employee_list.sort(key=lambda x: x['employee_name'])
        return employee_list

    @api.multi
    def generate_excel(self):
        """
        Generate an excel report of holiday reserves for all employees at wizard's date
        :return: a base64 encoded file as a str
        """
        if platform == 'win32':
            xls_flocation = u'\\static\\src\\excel\\Atostogų likučiai.xls'
            bottom_xls_flocation = u'\\static\\src\\excel\\atostogu_likuciai_bottom.xls'
        else:
            xls_flocation = u'/static/src/excel/Atostogų likučiai.xls'
            bottom_xls_flocation = u'/static/src/excel/atostogu_likuciai_bottom.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        bottom_file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + bottom_xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        bottom_rb = xlrd.open_workbook(bottom_file_loc, formatting_info=True)
        rb_sheet = rb.sheet_by_index(0)
        bottom_rb_sheet = bottom_rb.sheet_by_index(0)
        wb, wstyle = copy2(rb)
        bottom_wb, bottom_wstyle = copy2(bottom_rb)
        sheet = wb.get_sheet(0)
        # Page Settings
        sheet.set_portrait(False)
        sheet.paper_size_code = 9
        sheet.print_scaling = 65
        sheet.horz_page_breaks = []
        company = self.env.user.company_id
        company_name = '%s (į/k %s)' % (company.name, company.company_registry)
        date_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        period = unicode(date_dt.strftime(u'DARBUOTOJŲ ATOSTOGINIŲ KAUPIMO SUVESTINĖ %Y %m %d'))
        setOutCell(sheet, 0, 0, company_name or '')
        setOutCell(sheet, 0, 1, period)
        # self.wb = wb
        # self.margin += 12
        employees = self._find_employees_who_do_not_perform_voluntary_internships_by_date()
        n_employees = len(employees)
        data = employees.get_holiday_reserve_info(self.date)
        for r, employee in enumerate(employees):
            row_vals = [r + 1, employee.tabelio_numeris, employee.name]
            row_vals.extend(data[employee.id][k] for k in ['remaining_leaves', 'vdu', 'reserve', 'sodra', 'total'])
            for c, val in enumerate(row_vals):
                xf_index = rb_sheet.cell_xf_index(3, c)
                cell_style = wstyle[xf_index]
                sheet.write(r + 4, c, val, cell_style)
        for c in range(8):
            xf_index = bottom_rb_sheet.cell_xf_index(0, c)
            cell_style = bottom_wstyle[xf_index]
            if c < 3:
                val = None
            else:
                letter = 'ABCDEFGH'[c]
                num_to = 4 + n_employees
                val = Formula('SUM(%s5:%s%s)' % (letter, letter, num_to))
            sheet.write(4 + n_employees, c, val, cell_style)
        f = StringIO.StringIO()
        wb.save(f)
        base64_file = f.getvalue().encode('base64')
        return base64_file

    @api.multi
    def export_excel(self):
        """ Download action for the generated excel document """
        base64_file = self.generate_excel()
        filename = 'Atostogų likučiai %s %s.xls' % (self.env.user.company_id.name, self.date)
        #TODO: remove this context behavior when we use other method for call
        if self._context.get('archive', False):
            return base64_file
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'atostoginiu.kaupiniu.wizard',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=atostoginiu.kaupiniu.wizard&res_id=%s&attach_id=%s' % (self.id,
                                                                                                          attach_id.id),
            'target': 'self',
        }

    @api.multi
    def button_generate_report(self):
        """
        Generate report, based on value stored in res.company determine
        whether to use threaded calculation or not
        :return: Result of specified method
        """
        filename = 'Atostogų likučiai %s %s' % (self.env.user.company_id.name, self.date)
        report = 'Atostogų kaupinių apskaitymas'

        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            return self.env['robo.report.job'].generate_report(
                self, 'generate_excel', report, returns='base64', forced_name=filename, forced_extension='xls')
        else:
            return self.export_excel()
