# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools

from odoo.addons.l10n_lt_payroll.model.darbuotojai import PROBATION_LAW_CHANGE_DATE


class HrPayslipWorkedDays(models.Model):

    _inherit = 'hr.payslip.worked_days'

    @api.multi
    def _amount(self):
        # These new calculations based on planned time (in hours) take affect from December 1st. 2021
        illness_days = self.filtered(lambda day: day.code == 'L' and day.payslip_id.date_from >= '2021-12-01')
        other_days = self.filtered(lambda day: day not in illness_days)

        # Compute amount for other days
        super(HrPayslipWorkedDays, other_days)._amount()

        if not illness_days:
            return

        days_to_compute_regularly = self.env['hr.payslip.worked_days']  # Computed by calling super later

        payslips = illness_days.mapped('payslip_id')

        number_of_paid_days = 2  # Number of days paid

        # Earliest a leave can start that we should pay for is one day less than the number of paid days before the
        # payslip start
        min_date_from = min(payslips.mapped('date_from'))
        min_date_from_dt = datetime.strptime(min_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        min_date_from_dt -= relativedelta(days=number_of_paid_days-1)
        min_date_from = min_date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        max_date_to = max(payslips.mapped('date_to'))

        # Find accumulative work time appointments in the period
        appointments = self.env['hr.contract.appointment'].search([
            ('employee_id', 'in', payslips.mapped('employee_id').ids),
            ('schedule_template_id.template_type', '=', 'sumine'),
            ('date_start', '<=', max_date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', min_date_from)
        ])

        # Adjust the employees to find illnesses only for the employees working by accumulative work time accounting
        employees = appointments.mapped('employee_id')

        # Find all illnesses (including sick leave continuations and not)
        illnesses = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', max_date_to),
            ('date_to_date_format', '>=', min_date_from),
            ('type', '=', 'remove'),
            ('employee_id', 'in', employees.ids),
            ('state', '=', 'validate'),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_sl').id),
            '|',
            ('on_probation', '=', False),
            ('date_to_date_format', '>=', PROBATION_LAW_CHANGE_DATE)
        ])

        if not illnesses:
            # No illnesses found - compute amount regularly for all of the illness days
            return super(HrPayslipWorkedDays, illness_days)._amount()

        # For employees that are not working by accumulative work time accounting in any of the periods.
        regular_payslip_illness_days = illness_days.filtered(lambda d: d.payslip_id.employee_id not in employees)
        days_to_compute_regularly |= regular_payslip_illness_days
        illness_days = illness_days.filtered(lambda d: d not in regular_payslip_illness_days)

        # Get the codes that classify as work time
        worked_time_codes = self.env['hr.payslip'].get_salary_work_time_codes().get('normal', list())

        # Find planned schedule days in the period of the holidays
        first_illness_start = min(illnesses.mapped('date_from_date_format'))
        last_illness_end = max(illnesses.mapped('date_to_date_format'))
        planned_schedule_days = self.env['work.schedule.day'].search([
            ('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
            ('employee_id', 'in', employees.ids),
            ('work_schedule_line_id.used_as_planned_schedule_in_calculations', '=', True),
            ('date', '<=', last_illness_end),
            ('date', '>=', first_illness_start),
            ('line_ids', '!=', False),
            ('line_ids.code', 'in', list(worked_time_codes))
        ])

        # Apply calculations by planned schedule days only for payslip days that have at least some planned days
        employees = planned_schedule_days.mapped('employee_id')
        days_to_compute_regularly |= illness_days.filtered(lambda d: d.payslip_id.employee_id not in employees)
        illness_days_to_compute_by_planned_schedule = illness_days.filtered(
            lambda d: d not in days_to_compute_regularly
        )

        # Compute the days that are not related to accumulative work time accounting
        super(HrPayslipWorkedDays, days_to_compute_regularly)._amount()

        for rec in illness_days_to_compute_by_planned_schedule:
            # Get basic payslip data
            payslip = rec.payslip_id
            payslip_date_from = payslip.date_from
            payslip_date_to = payslip.date_to
            employee = payslip.employee_id
            contract = payslip.contract_id

            total_amount = 0.0

            # To include hr.holiday records for illnesses that are continuations
            payslip_date_from_dt = datetime.strptime(payslip_date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            minimum_illness_end_date_dt = payslip_date_from_dt - relativedelta(days=number_of_paid_days-1)
            minimum_illness_end_date = minimum_illness_end_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            employee_illnesses_in_payslip_period = illnesses.filtered(
                lambda i: i.date_from_date_format <= payslip_date_to and
                          i.date_to_date_format >= minimum_illness_end_date and
                          i.employee_id == employee
            )
            if not employee_illnesses_in_payslip_period:
                continue

            # Find out all of the illness periods based on sick leave continuation
            illnesses_by_period = employee_illnesses_in_payslip_period.get_illness_periods()

            illness_coefficient = payslip.company_id.with_context(date=payslip_date_to).ligos_koeficientas

            for employee_illnesses in illnesses_by_period:
                period_from = min(employee_illnesses.mapped('date_from_date_format'))
                period_to = max(employee_illnesses.mapped('date_to_date_format'))

                first_illness_rec_of_period = employee_illnesses.sorted(key=lambda i: i.date_from_date_format)[0]
                if period_from < payslip_date_from and first_illness_rec_of_period.sick_leave_continue:
                    # The original illness was not included in illnesses meaning that this illness period started before
                    # the date of which this period would still be compensated by employer and the sick leave
                    # continuation should be skipped.
                    continue

                # Find the period that is paid
                paid_period_from = max(period_from, payslip_date_from)
                period_from_dt = datetime.strptime(period_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                maximum_paid_period_to_dt = period_from_dt + relativedelta(days=number_of_paid_days-1)
                maximum_paid_period_to = maximum_paid_period_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                paid_period_to = min(period_to, payslip_date_to, maximum_paid_period_to)

                if paid_period_to < paid_period_from:
                    continue  # It's a sick leave continuation and the leave has been paid for in full in previous slips

                # Calculate how many work days fall under work days in previous month
                period_to_dt = datetime.strptime(paid_period_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                potential_date_dt = period_from_dt
                total_days_previous_month = total_days_current_month = 0
                first_day_previous_month = first_day_this_month = None
                while potential_date_dt <= period_to_dt:
                    potential_date = potential_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    potential_date_dt += relativedelta(days=1)
                    # Skip dates where the employee is on probation before the probation period law change date
                    related_illness = employee_illnesses.filtered(
                        lambda h: h.date_from_date_format <= potential_date <= h.date_to_date_format
                    )
                    if related_illness and related_illness[0].on_probation and potential_date < PROBATION_LAW_CHANGE_DATE:
                        continue
                    is_work_day = self.env['hr.employee'].is_work_day(
                        potential_date, employee.id, contract_id=contract.id
                    )
                    if is_work_day:
                        if potential_date < payslip_date_from:
                            total_days_previous_month += 1
                            if not first_day_previous_month:
                                first_day_previous_month = potential_date
                        else:
                            total_days_current_month += 1
                            if not first_day_this_month:
                                first_day_this_month = potential_date

                planned_days = planned_schedule_days.filtered(
                    lambda d: d.employee_id == employee and paid_period_from <= d.date <= paid_period_to
                )
                if not planned_days:
                    # No planned days are used so we should compute the amount regularly
                    if total_days_previous_month:
                        vdu = payslip.with_context(vdu_type='d', forced_vdu_date=first_day_previous_month).vdu0
                    else:
                        vdu = payslip.with_context(vdu_type='d', forced_vdu_date=first_day_this_month).vdu_previous

                    if payslip.struct_id.code == 'MEN':
                        pay_per_day = max(illness_coefficient * vdu, 0.0)
                    elif payslip.struct_id.code == 'VAL':
                        min_day_pay = contract.employee_id.get_minimum_wage_for_date(payslip_date_to)['day']
                        pay_per_day = max(min_day_pay, vdu)
                        pay_per_day = pay_per_day * illness_coefficient
                    else:
                        pay_per_day = 0.0

                    illness_amount = pay_per_day * total_days_current_month
                    total_amount += illness_amount
                    continue

                planned_lines = planned_days.mapped('line_ids').filtered(lambda l: str(l.code) in worked_time_codes)
                if not planned_lines:
                    # Days exist but there's no planned time set so the employee should not be paid anything
                    continue

                planned_work_time_duration = sum(planned_lines.mapped('worked_time_total'))

                # Determine which VDU to use
                if total_days_previous_month:
                    vdu = payslip.with_context(vdu_type='h', forced_vdu_date=first_day_previous_month).vdu0
                else:
                    vdu = payslip.with_context(vdu_type='h', forced_vdu_date=first_day_this_month).vdu_previous

                illness_amount = illness_coefficient * vdu * planned_work_time_duration
                total_amount += illness_amount

            rec.amount = total_amount
