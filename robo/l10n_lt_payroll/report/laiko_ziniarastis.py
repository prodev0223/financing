# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import exceptions
from odoo import models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


class HrHolidaySummaryReport(models.AbstractModel):

    _name = 'report.l10n_lt_payroll.report_laiko_ziniarastis_sl'

    def _get_header_info(self, start_date, date_to, holiday_type):
        return {
            'start_date': start_date,
            'end_date': date_to,
            'holiday_type': holiday_type
        }

    @api.model
    def _get_day(self, start_date, end_date):
        res = []
        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        iseigines = self.env['sistema.iseigines'].search([('date', '>=', start_date), ('date', '<=', end_date)])
        iseigines_data = []
        for iseigine in iseigines:
            iseigines_data.append(iseigine.date)
        for x in range(0, ((end_date-start_date).days+1)):
            color = '#ababab' if start_date.strftime('%a') == 'Sat' or start_date.strftime('%a') == 'Sun' else ''
            kodas = 'P' if start_date.strftime('%a') == 'Sat' or start_date.strftime('%a') == 'Sun' else ''
            if start_date.strftime("%Y-%m-%d") in iseigines_data:
                color = '#ababab'
            res.append({'day_str': start_date.strftime('%a'), 'day': start_date.day, 'color': color, 'kodas': kodas})
            start_date = start_date + relativedelta(days=1)
        return res

    def _get_months(self, start_date, end_date):
        # it works for geting month name between two dates.
        res = []
        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        while start_date <= end_date:
            last_date = start_date + relativedelta(day=1, months=+1, days=-1)
            if last_date > end_date:
                last_date = end_date
            month_days = (last_date - start_date).days + 1
            res.append({'month_name': start_date.strftime('%B'), 'days': month_days})
            start_date += relativedelta(day=1, months=+1)
        return res

    @api.multi
    def _get_leaves_summary(self, start_date, end_date, empid, holiday_type):
        res = []
        count = 0
        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        iseigines = self.env['sistema.iseigines'].search([('date', '>=', start_date), ('date', '<=', end_date)])
        iseigines_data = []
        iseigines_data2 = []
        if len(iseigines) > 0:
            for iseigine in iseigines:
                iseigines_data2.append(iseigine.date)
                savaites_diena = datetime.strptime(iseigine.date, '%Y-%m-%d').weekday()
                if 1 <= savaites_diena <= 5:
                    temp = datetime.strptime(iseigine.date, '%Y-%m-%d') - timedelta(1)
                    iseigines_data.append(temp.strftime("%Y-%m-%d"))

        for index in range(0, ((end_date-start_date).days+1)):
            current = start_date + timedelta(index)
            res.append({'day': current.day, 'color': '', 'kodas': '', 'minus': '', 'nedirba': ''})
            if current.strftime('%a') == 'Sat' or current.strftime('%a') == 'Sun':
                res[index]['color'] = '#ababab'
                res[index]['kodas'] = 'P'
            if current.strftime("%Y-%m-%d") in iseigines_data:
                res[index]['minus'] = 1
            if current.strftime("%Y-%m-%d") in iseigines_data2:
                res[index]['color'] = '#ababab'
                res[index]['kodas'] = 'P'

        # count and get leave summary details.
        holiday_type = ['confirm', 'validate'] if holiday_type == 'both' else ['confirm'] if holiday_type == 'Confirmed' else ['validate']
        holidays = self.env['hr.holidays'].search([('employee_id', '=', empid),
                                                   ('state', 'in', holiday_type),
                                                   ('type', '=', 'remove'),
                                                   ('date_from', '<=', str(end_date)),
                                                   ('date_to', '>=', str(start_date))])
        end_date2 = end_date + timedelta(1)
        for holiday in holidays:
            date_from = datetime.strptime(holiday.date_from, DEFAULT_SERVER_DATETIME_FORMAT)
            date_to = datetime.strptime(holiday.date_to, DEFAULT_SERVER_DATETIME_FORMAT)
            for index in range(0, ((date_to - date_from).days + 1)):
                if start_date <= date_from <= end_date2:
                    res[(date_from-start_date).days]['color'] = holiday.holiday_status_id.color_name
                    if holiday.holiday_status_id.kodas == 'FD':
                        res[(date_from-start_date).days]['kodas'] = 'K'
                    else:
                        res[(date_from-start_date).days]['kodas'] = holiday.holiday_status_id.kodas
                    count += 1
                date_from += timedelta(1)
        self.sum = count

        return res

    @api.multi
    def _get_data_from_report(self, data):
        res = []
        emp_obj = self.env['hr.employee']
        # department_obj = self.env['hr.department']
        ziniarastis_line_obj = self.env['ziniarastis.period.line']
        employees = data['emp']
        res.append({'data': []})
        # for emp in employees:
        #     payslip = payslip_obj.search([('employee_id', '=', emp.id),
        #                                   ('date_from', '>=', data['date_from']),
        #                                   ('date_to', '<=', data['date_to'])])
        #     if not payslip:
        #         continue
        #     res[0]['data'].append({
        #         'emp': emp.name,
        #         'display': self._get_leaves_summary(data['date_from'], data['date_to'], emp.id, data['holiday_type']),
        #         'sum': self.sum,
        #         'employee_id': emp,
        #         'payslip_id': payslip,
        #     })
        return res

    @api.multi
    def _get_holidays_status(self):
        res = []
        holiday_obj = self.env['hr.holidays.status']
        holiday_datas = holiday_obj.search([])
        for holiday in holiday_datas:
            res.append({'color': holiday.color_name, 'name': holiday.name})
        return res

    # def _max_laikas_d(self, payslips):
    #     suma_d = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             suma_d = suma_d + line.number_of_days
    #     return suma_d or 0
    #
    # def _max_laikas_h(self, payslips):
    #     suma_h = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             suma_h = suma_h + line.number_of_hours
    #     return suma_h or 0
    #
    # def _visas_laikas_d(self, payslips):
    #     suma_d = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             if payslip.struct_id.code == 'MEN':
    #                 if line.code == 'FD' or line.code == 'A':
    #                     suma_d = suma_d + line.number_of_days
    #             elif payslip.struct_id.code == 'VAL':
    #                 if line.code in ['FD', 'A', 'DN', 'VSS', 'VD', 'PLS']:
    #                     suma_d = suma_d + line.number_of_days
    #     return suma_d
    #
    # def _visas_laikas_h(self, payslips):
    #     suma_h = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             if payslip.struct_id.code == 'MEN':
    #                 if line.code == 'FD' or line.code == 'A':
    #                     suma_h = suma_h + line.number_of_hours
    #             elif payslip.struct_id.code == 'VAL':
    #                 if line.code in ['FD', 'A', 'DN', 'VSS', 'VD', 'PLS']:
    #                     suma_h = suma_h + line.number_of_hours
    #     return suma_h
    #
    # def _nemokamos_atostogos_d(self, payslips):
    #     suma_d = 0
    #     suma_dd = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             suma_dd = suma_dd + line.number_of_days
    #             if payslip.struct_id.code == 'MEN':
    #                 if line.code == 'FD' or line.code == 'A':
    #                     suma_d = suma_d + line.number_of_days
    #             elif payslip.struct_id.code == 'VAL':
    #                 if line.code in ['FD', 'A', 'DN', 'VSS', 'VD', 'PLS']:
    #                     suma_d = suma_d + line.number_of_days
    #     suma_d = suma_dd - suma_d
    #     return suma_d or 0
    #
    # def _nemokamos_atostogos_h(self, payslips):
    #     suma_h = 0
    #     suma_hh = 0
    #     for payslip in payslips:
    #         for line in payslip.worked_days_line_ids:
    #             suma_hh = suma_hh + line.number_of_hours
    #             if payslip.struct_id.code == 'MEN':
    #                 if line.code == 'FD' or line.code == 'A':
    #                     suma_h = suma_h + line.number_of_hours
    #             elif payslip.struct_id.code == 'VAL':
    #                 if line.code in ['FD', 'A', 'DN', 'VSS', 'VD', 'PLS']:
    #                     suma_h = suma_h + line.number_of_hours
    #     suma_h = suma_hh - suma_h
    #     return suma_h or 0

    def _line_number(self):
        try:
            self.nr += 1
        except AttributeError:
            self.nr = 1
            return self.nr
        return self.nr

    def _numusti(self):
        try:
            del self.nr
        except:
            pass

    # def _replace(self, string):
    #     string = str(string)
    #     if len(string) > 0 and '.' in string:
    #         return string.replace('.', ',')
    #     else:
    #         return string
    #
    # def _remove(self, string):
    #     string = str(string)
    #     if len(string) > 0 and '.' in string:
    #         return string.split('.')[0]
    #     else:
    #         return string

    def _nustatyti_laika(self, data2):
        data1 = str(self.data_nuo or '')
        data2 = str(data2)
        if not data1 or not data2:
            return False
        data1_dt = datetime.strptime(data1, DEFAULT_SERVER_DATE_FORMAT)
        data2_dt = datetime.strptime(data2, DEFAULT_SERVER_DATE_FORMAT)
        if data1_dt.year == data2_dt.year and data1_dt.month == data2_dt.month:
            return True
        else:
            return False

    def _langelis(self, emp_id, details):
        day = details['day']
        minus = details['minus']
        kodas = details['kodas']
        if kodas:
            return kodas
        else:
            data_nuo = self.data_nuo
            data_nuo_dt = datetime.strptime(data_nuo, DEFAULT_SERVER_DATE_FORMAT)
            data_dt = datetime(data_nuo_dt.year, data_nuo_dt.month, day)
            data = data_dt.strftime(DEFAULT_SERVER_DATE_FORMAT)
            cr = self._cr
            cr.execute("select id from hr_contract where employee_id = %s and "
                       "date_start <= %s and (date_end is NULL or date_end >= %s)",
                       (emp_id.id, data, data))
            ids = cr.fetchone()
            if ids and ids[0]:
                cid = ids[0]
                contract = self.env['hr.contract'].sudo().browse(cid)
                if contract.working_hours:
                    dt = data_dt - relativedelta(days=1)
                    hours = int(contract.working_hours.get_working_hours(dt, dt)[0])
                    if hours >= 8 and not minus:
                        return hours
                    elif hours >= 8 and minus:
                        return hours-1
                    elif hours < 8:
                        return hours
                else:
                    return 8
            else:
                return ' '

    @api.multi
    def render_html(self, doc_ids, data=None):
        if len(doc_ids) > 1:
            raise exceptions.UserError(_('Negalima spausdinti daugiau kaip vieno žiniaraščio'))
        report_obj = self.env['report']
        ziniaratis_period_obj = self.env['ziniarastis.period']
        ziniarastis_period = ziniaratis_period_obj.browse(doc_ids)[0]
        holidays_report = report_obj._get_report_from_name('l10n_lt_payroll.report_laiko_ziniarastis_sl')
        data = {}
        data['form'] = {}
        data['form']['date_from'] = ziniarastis_period.date_from
        self.data_nuo = data['form']['date_from']
        data['form']['date_to'] = ziniarastis_period.date_to
        data['form']['holiday_type'] = 'validate'
        data['form']['emp'] = self.env['hr.employee'].search([])
        # docargs = {
        #     'doc_ids': doc_ids,
        #     'doc_model': holidays_report.model,
        #     'docs': ziniarastis_period,
        #     'get_header_info': self._get_header_info(data['form']['date_from'], data['form']['date_to'], data['form']['holiday_type']),
        #     'get_day': self._get_day(data['form']['date_from'], data['form']['date_to']),
        #     'get_months': self._get_months(data['form']['date_from'], data['form']['date_to']),
        #     'get_data_from_report': self._get_data_from_report(data['form']),
        #     'get_holidays_status': self._get_holidays_status(),
        #     'max_laikas_d': self._max_laikas_d,
        #     'max_laikas_h': self._max_laikas_h,
        #     'visas_laikas_d': self._visas_laikas_d,
        #     'visas_laikas_h': self._visas_laikas_h,
        #     'nemokamos_atostogos_d': self._nemokamos_atostogos_d,
        #     'nemokamos_atostogos_h': self._nemokamos_atostogos_h,
        #     'line_number': self._line_number,
        #     'numusti_nr': self._numusti,
        #     'replace': self._replace,
        #     'remove': self._remove,
        #     'nustatyti_laika': self._nustatyti_laika,
        #     'langelis': self._langelis,
        # }
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': holidays_report.model,
            'docs': ziniarastis_period,
            # 'get_header_info': self._get_header_info(data['form']['date_from'], data['form']['date_to'],
            #                                          data['form']['holiday_type']),
            'get_day': self._get_day(data['form']['date_from'], data['form']['date_to']),
            'get_months': self._get_months(data['form']['date_from'], data['form']['date_to']),
            # 'get_data_from_report': self._get_data_from_report(data['form']),
            # 'get_holidays_status': self._get_holidays_status(),
            # 'max_laikas_d': self._max_laikas_d,
            # 'max_laikas_h': self._max_laikas_h,
            # 'visas_laikas_d': self._visas_laikas_d,
            # 'visas_laikas_h': self._visas_laikas_h,
            # 'nemokamos_atostogos_d': self._nemokamos_atostogos_d,
            # 'nemokamos_atostogos_h': self._nemokamos_atostogos_h,
            'line_number': self._line_number,
            # 'numusti_nr': self._numusti,
            # 'replace': self._replace,
            'remove': self._remove,
            # 'nustatyti_laika': self._nustatyti_laika,
            'langelis': self._langelis,
        }
        return self.env['report'].render('l10n_lt_payroll.report_laiko_ziniarastis_sl', docargs)
