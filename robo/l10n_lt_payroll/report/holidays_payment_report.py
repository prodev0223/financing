# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from datetime import datetime


class HrHolidaysPaymentReport(models.Model):

    _name = 'hr.holidays.payment.report'
    _description = _('Holidays report')

    _auto = False

    contract_id = fields.Many2one('hr.contract', string='Kontraktas')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas')
    vdu = fields.Float(string='VDU')
    bruto = fields.Float(string='Bruto')
    date_from = fields.Date(string='Laikotarpis nuo')
    date_to = fields.Date(string='Laikotarpis iki')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'hr_holidays_payment_report')
        self._cr.execute('''
            CREATE OR REPLACE VIEW hr_holidays_payment_report AS (
            SELECT
                pay_line.id as id,
                hr_holidays.contract_id as contract_id,
                hr_holidays.employee_id as employee_id,
                pay_line.vdu as vdu,
                pay_line.period_date_from as date_from,
                pay_line.period_date_to as date_to,
                pay_line.amount as bruto
            FROM hr_holidays_payment_line pay_line
                JOIN hr_holidays ON pay_line.holiday_id = hr_holidays.id
            WHERE hr_holidays.state = 'validate'
            )
            ''')


HrHolidaysPaymentReport()
