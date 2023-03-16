# -*- coding: utf-8 -*-

from odoo import api, models, tools
from odoo.addons.l10n_lt_payroll.model.work_norm import CODES_ABSENCE, CODES_HOLIDAYS


class ContractAppointment(models.Model):

    _inherit = 'hr.contract.appointment'

    @api.multi
    def get_shorter_before_holidays_worked_time_data(self, date):
        """
            Gets specific work time date for shorter before holidays to determine if the date should be shortened. First
            checks if ziniarastis period line has some data and if so returns that otherwise checks what's on the
            schedule ignoring the state of the schedule.
        """
        self.ensure_one()
        # Get data from ziniarastis
        res = super(ContractAppointment, self).get_shorter_before_holidays_worked_time_data(date)
        if res.get('some_time_for_period_line_is_set'):
            return res
        WorkScheduleDay = self.env['work.schedule.day']
        domain = [('employee_id', '=', self.employee_id.id), ('date', '=', date)]
        # No data on ziniarastis is set
        res = {'some_time_for_period_line_is_set': False, 'worked_time_for_day': 0.0,
               'leave_is_set_in_planned_schedule': False}
        # Find factual work time days for date (multiple days due to possibly multiple departments)
        factual_work_schedule_days = WorkScheduleDay.search(
            domain + [('work_schedule_id', '=', self.env.ref('work_schedule.factual_company_schedule').id)]
        )
        if not factual_work_schedule_days:
            # Nothing is set
            return res
        skipped_codes = CODES_HOLIDAYS + CODES_ABSENCE
        # Any day has lines with work times that are not in skipped codes list
        res['some_time_for_period_line_is_set'] = not tools.float_is_zero(
            sum(factual_work_schedule_days.mapped('work_schedule_line_id.day_ids.line_ids').filtered(
                lambda l: l.code not in skipped_codes
            ).mapped('worked_time_total')), precision_digits=2
        )
        # Any holiday in planned work schedule
        planned_work_schedule_days = WorkScheduleDay.search(
            domain + [('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id)]
        )
        res['leave_is_set_in_planned_schedule'] = True if planned_work_schedule_days.\
            mapped('work_schedule_line_id.day_ids.line_ids').filtered(
                lambda l: l.code in CODES_HOLIDAYS and l.day_id.date == date
        ) else False
        # Total worked time for lines with codes not in skipped list
        res['worked_time_for_day'] = sum(factual_work_schedule_days.mapped('line_ids').filtered(
            lambda l: l.code not in skipped_codes
        ).mapped('worked_time_total'))
        return res
