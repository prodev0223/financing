# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_atsaukimo_is_kasmetiniu_atostogu_workflow(self):
        self.ensure_one()
        holiday_status_id = self.env.ref('hr_holidays.holiday_status_cl').id
        holiday = self.env['hr.holidays'].search([
            ('state', '=', 'validate'),
            ('type', '=', 'remove'),
            ('employee_id', '=', self.employee_id2.id),
            ('date_to_date_format', '>=', self.date_1),
            ('date_from_date_format', '<=', self.date_1),
            ('holiday_status_id', '=', holiday_status_id)
        ])

        if holiday:
            if holiday.date_from_date_format == self.date_1:
                holiday.action_refuse()
            else:
                date = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
                date -= relativedelta(days=1)
                holiday.stop_in_the_middle(date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))

            holiday_to_move = self.env['hr.holidays'].search([
                ('state', '=', 'validate'),
                ('type', '=', 'remove'),
                ('employee_id', '=', self.employee_id2.id),
                ('date_to_date_format', '=', self.date_from),
                ('date_from_date_format', '=', self.date_to),
                ('holiday_status_id', '=', holiday_status_id)
            ])

            if not holiday_to_move:
                moved_holiday = self.env['hr.holidays'].create({
                    'name': 'Kasmetinės atostogos',
                    'data': self.date_document,
                    'employee_id': self.employee_id2.id,
                    'holiday_status_id': holiday_status_id,
                    'date_from': self.calc_date_from(self.date_from),
                    'date_to': self.calc_date_to(self.date_to),
                    'type': 'remove',
                    'numeris': self.document_number,
                    'ismokejimas': holiday.ismokejimas,
                })
                moved_holiday.action_approve()
                self.inform_about_creation(moved_holiday)
                self.write({
                    'record_model': 'hr.holidays',
                    'record_id': moved_holiday.id,
                })


EDocument()
