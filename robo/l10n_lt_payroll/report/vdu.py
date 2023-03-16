# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _, tools
from odoo.tools.misc import formatLang
from odoo.addons.l10n_lt_payroll.model.darbuotojai import get_vdu
from datetime import datetime


class VDUReport(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.report_vdu'

    def get_data(self, doc_ids, data=None):
        if not doc_ids:
            doc_ids = []
        employee_ids = doc_ids + data.get('doc_ids', []) + data.get('context', {}).get('employee_ids', [])
        employees = self.env['hr.employee'].sudo().browse(set(employee_ids))

        if not self.env.user.is_manager() and not self.env.user.is_hr_manager():
            employees = employees.filtered(lambda e: e.id in self.env.user.partner_id.employee_ids.ids)

        if not employees:
            raise exceptions.UserError(_('Unable to determine employees to generate report for'))

        employees = employees.sorted(key=lambda e: e.name)

        self = self.sudo()

        date = str(data.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))

        vdu_data = []
        for employee in employees:
            day_vdu_data = get_vdu(self.env, date, employee, vdu_type='d')
            hourly_vdu_data = get_vdu(self.env, date, employee, vdu_type='h')

            vdu_record_data = day_vdu_data.get('salary_info', {}).get('vdu_record_data', {})
            vdu_record_list = []
            if vdu_record_data:
                vdu_record_dates = vdu_record_data.keys()
                vdu_record_dates.sort(reverse=True)
                for vdu_rec_date in vdu_record_dates:
                    vdu_rec_data = vdu_record_data.get(vdu_rec_date)
                    vdu_rec_data.update({'date': vdu_rec_date})
                    vdu_record_list.append(vdu_rec_data)
            day_vdu_data['salary_info'].update({'vdu_record_data': vdu_record_list})

            vdu_data.append({
                'employee': employee,
                'vdu_d': day_vdu_data.get('vdu', 0.0),
                'vdu_h': hourly_vdu_data.get('vdu', 0.0),
                'salary_info': day_vdu_data.get('salary_info', {}),
                'minimum_wage_adjustment_d': day_vdu_data.get('minimum_wage_adjustment', {}),
                'minimum_wage_adjustment_h': hourly_vdu_data.get('minimum_wage_adjustment', {}),
                'calculation_info_d': day_vdu_data.get('calculation_info', {}),
                'calculation_info_h': hourly_vdu_data.get('calculation_info', {}),
            })
        return vdu_data

    @api.multi
    def render_html(self, doc_ids, data=None):
        vdu_data = self.get_data(doc_ids, data)
        date = str(data.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        return self.env['report'].render('l10n_lt_payroll.report_vdu', {
            'docs': vdu_data,
            'date': date,
            'doc_model': 'report.l10n_lt_payroll.report_vdu',
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw)
        })
