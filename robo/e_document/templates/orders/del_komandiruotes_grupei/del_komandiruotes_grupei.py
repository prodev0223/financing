# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_komandiruotes_grupei_workflow(self):
        self.ensure_one()
        isakymo_nr = self.document_number

        lines = self.e_document_line_ids
        for line in lines:
            hol_id = self.env['hr.holidays'].create({
                'name': 'Tarnybinės komandiruotės',
                'data': self.date_document,
                'employee_id': line.employee_id2.id,
                'holiday_status_id': self.env.ref('hr_holidays.holiday_status_K').id,
                'date_from': self.calc_date_from(self.date_from),
                'date_to': self.calc_date_to(self.date_to),
                'type': 'remove',
                'numeris': isakymo_nr,
                'country_allowance_id': self.country_allowance_id.id,
                'amount_business_trip': line.float_1,
                'business_trip_worked_on_weekends': True if self.business_trip_worked_on_weekends == 'true' else False,
            })
            hol_id.action_approve()


EDocument()
