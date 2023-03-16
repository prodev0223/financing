# -*- coding: utf-8 -*-

from odoo import models, api


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @api.multi
    def get_special_hours_from_schedule(self, res, date_from, date_to):
        contract_id = res['value']['contract_id']
        contract = self.env['hr.contract'].browse(contract_id)
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        if not contract:
            return {'DN': {},
                    'DP': {},
                    'SNV': {},
                    }
        schedule_days = self.env['work.schedule.day'].search([
            ('date', '<=', date_to),
            ('date', '>=', date_from),
            ('employee_id', '=', contract.employee_id.id),
            ('work_schedule_id', '=', factual_work_schedule.id)
        ])
        return self.env['work.schedule.day'].calculate_special_hours(schedule_days, contract)

HrPayslip()
