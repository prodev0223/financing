# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import models, api, tools
from six import iteritems


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_komandiruotes_workflow(self):
        self.ensure_one()
        isakymo_nr = self.document_number
        hol_id = self.env['hr.holidays'].create({
            'name': 'Tarnybinės komandiruotės',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_K').id,
            'date_from': self.calc_date_from(self.date_from),
            'date_to': self.calc_date_to(self.date_to),
            'type': 'remove',
            'numeris': isakymo_nr,
            'country_allowance_id': self.country_allowance_id.id,
            'amount_business_trip': self.float_1,
            'business_trip_worked_on_weekends': True if self.dates_contain_weekend and self.business_trip_worked_on_weekends == 'true' else False
        })
        hol_id.action_approve()
        self.inform_about_creation(hol_id)

        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })

        if self.dates_contain_weekend and self.business_trip_worked_on_weekends == 'true' and self.compensate_employee_business_trip_holidays == 'free_days':
            compensation_days = self.get_compensation_days(self.date_from, self.date_to, self.employee_id2.id)
            for compensation_date_from, compensation_date_to in iteritems(compensation_days):
                hol_id = self.env['hr.holidays'].create({
                    'name': 'Poilsio dienos už komandiruotėje dirbtas poilsio dienas',
                    'data': self.date_document,
                    'employee_id': self.employee_id2.id,
                    'holiday_status_id': self.env.ref('hr_holidays.holiday_status_V').id,
                    'date_from': self.calc_date_from(compensation_date_from),
                    'date_to': self.calc_date_to(compensation_date_to),
                    'type': 'remove',
                    'numeris': isakymo_nr,
                })
                hol_id.action_approve()
                self.inform_about_creation(hol_id)
        elif self.dates_contain_weekend and self.business_trip_worked_on_weekends == 'true' and self.compensate_employee_business_trip_holidays != 'free_days':
            num_compensation_days_to_add = self.get_num_of_compensation_days(self.date_from, self.date_to)
            date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            holiday_fix = self.env['hr.holidays.fix'].adjust_fix_days(self.employee_id2, date, num_compensation_days_to_add)
            if holiday_fix:
                self.write({'holiday_fix_id': holiday_fix.id})


EDocument()
