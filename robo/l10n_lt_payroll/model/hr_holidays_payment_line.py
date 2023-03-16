# -*- coding: utf-8 -*-

from odoo import api, models, tools


class HrHolidaysPaymentLine(models.Model):
    _inherit = 'hr.holidays.payment.line'

    @api.model
    def _get_payment_amount_adjusted_by_usage_lines(self, usage_lines, vdu, holiday_coefficient, num_work_days, cutoff):
        """
            Calculates the bruto amount for a holiday payment line based on holiday usage lines.
        Returns:
            float: What the bruto should be for the payment line based on holiday usage lines
        """

        # Safety net - total amount of days in usage lines should never be more than the number of days in the
        # record.
        max_days_to_calculate_for = num_work_days

        amount_bruto = 0.0
        for usage_line in usage_lines:
            used_days = usage_line.used_days
            used_days = min(used_days, max_days_to_calculate_for)
            max_days_to_calculate_for -= used_days
            amount_bruto += used_days * usage_line.vdu

        # If the usage lines don't cover all of the days to calculate for we calculate the theoretical payment based on
        # accumulation records
        if tools.float_compare(max_days_to_calculate_for, 0.0, precision_digits=2) > 0:
            employees = usage_lines.mapped('holiday_id.employee_id')
            employee = employees and employees[0]
            if employee:
                # Find accumulations with a balance and sort them
                holiday_accumulations = self.env['hr.employee.holiday.accumulation'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '>=', cutoff)
                ]).filtered(
                    lambda accumulation: tools.float_compare(
                        accumulation.accumulation_work_day_balance,
                        0.0,
                        precision_digits=2
                    ) >= 0
                ).sorted(key=lambda accumulation: accumulation.date_from)

                for holiday_accumulation in holiday_accumulations:
                    balance = holiday_accumulation.accumulation_work_day_balance
                    theoretically_used_days = min(balance, max_days_to_calculate_for)
                    max_days_to_calculate_for -= theoretically_used_days
                    amount_bruto += theoretically_used_days * vdu * holiday_accumulation.post

        # Add the amount for the days that the employee is taking in advance and is not fulfilled by the accumulation
        # records
        max_days_to_calculate_for = max(max_days_to_calculate_for, 0.0)
        amount_bruto += vdu * max_days_to_calculate_for * holiday_coefficient

        return amount_bruto
