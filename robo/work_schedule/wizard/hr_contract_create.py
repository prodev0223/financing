# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api


class HrContractCreate(models.TransientModel):
    _inherit = 'hr.contract.create'

    @api.multi
    def create_contract(self):
        """
            Creates work schedule for current and next month when contract is created. Work schedule for other months is
            created by a CRON job.
        """

        res = super(HrContractCreate, self).create_contract()  # Ensures (self) one

        # Determine dates
        now = datetime.now()
        current_month, current_year = now.month, now.year
        next_month = now + relativedelta(months=1)
        next_month, next_year = next_month.month, next_month.year

        employee = self.employee_id
        department = employee.department_id

        # Find work schedule lines
        work_schedule_lines = self.env['work.schedule.line'].sudo().search([
            ('employee_id', '=', employee.id),
            '|',
            '&',
            ('year', '=', current_year),
            ('month', '=', current_month),
            '&',
            ('year', '=', next_year),
            ('month', '=', next_month)
        ])

        factual_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')

        factual_line_for_current_month = work_schedule_lines.filtered(
            lambda line: line.year == current_year and line.month == current_month and
                         line.work_schedule_id == factual_schedule
        )

        planned_line_for_next_month = work_schedule_lines.filtered(
            lambda line: line.year == next_year and line.month == next_month and
                         line.work_schedule_id == planned_schedule
        )

        if not factual_line_for_current_month:
            factual_schedule.sudo().create_empty_schedule(
                current_year, current_month, [employee.id], [department.id], bypass_validated_time_sheets=True
            )

        if not planned_line_for_next_month:
            planned_schedule.sudo().create_empty_schedule(
                next_year, next_month, [employee.id], [department.id], bypass_validated_time_sheets=True
            )

        return res
