# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeHolidayUsage(models.Model):
    _name = 'hr.employee.holiday.usage'

    def _get_holiday_domain(self):
        return "[('holiday_status_id', '=', {})]".format(self.env.ref('hr_holidays.holiday_status_cl').id)

    holiday_id = fields.Many2one('hr.holidays', string='Holiday', required=True, readonly=True,
                                 domain=_get_holiday_domain, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Employee', related='holiday_id.employee_id', store=True,
                                  inverse='_recompute_holiday_usage')
    confirmed = fields.Boolean('Confirmed', compute='_compute_confirmed', store=True)
    line_ids = fields.One2many('hr.employee.holiday.usage.line', 'usage_id', string='Holiday usage lines')
    used_days = fields.Float(string='Used holiday work days (from holidays)', compute='_compute_used_days')
    accumulation_assigned_days = fields.Float(string='Work days assigned to accumulations',
                                              compute='_compute_used_days')
    leaves_accumulation_type = fields.Selection([('work_days', 'Darbo dienomis'),
                                                 ('calendar_days', 'Kalendorinėmis dienos')],
                                                string='Leaves accumulation type',
                                                related='holiday_id.leaves_accumulation_type', store=True)
    date_from = fields.Date(string='Holiday date from', related='holiday_id.date_from_date_format', readonly=True,
                            store=True)
    date_to = fields.Date(string='Holiday date to', related='holiday_id.date_to_date_format', readonly=True,
                          store=True)
    current_holiday_duration = fields.Float(string='Used days to current date',
                                            compute='_compute_current_holiday_duration')

    @api.multi
    @api.depends('holiday_id.state')
    def _compute_confirmed(self):
        for rec in self:
            rec.confirmed = rec.holiday_id.state == 'validate'

    @api.multi
    def name_get(self):
        return [(
            usage.id,
            _('{} holiday usage for holidays from {} to {}').format(
                usage.employee_id.name,
                usage.date_from,
                usage.date_to,
            )
        ) for usage in self]

    @api.multi
    @api.constrains('holiday_id')
    def _check_single_usage_for_single_holiday(self):
        if self.search_count([
            ('id', 'not in', self.ids),
            ('holiday_id', 'in', self.mapped('holiday_id').ids)
        ]):
            raise exceptions.UserError(_('Only one holiday usage record can exist for a single holiday record'))

    @api.multi
    def _recompute_holiday_usage(self):
        """
            Recomputes holiday usage using holiday accumulation records
        """

        # Inverse triggers recompute on record creation and we sometimes want it only when all usage records have been
        # created
        if not self._context.get('recompute', True):
            return

        HrEmployeeHolidayAccumulation = self.env['hr.employee.holiday.accumulation']

        # Unlink all lines since they are the records that have to be recreated/recomputed
        lines = self.mapped('line_ids')
        lines._compute_has_confirmed_payslip()
        forced_recompute_date = self._context.get('forced_recompute_date')
        if self._context.get('force_recompute_confirmed') or forced_recompute_date:
            lines_to_unlink = lines
            if forced_recompute_date:
                lines_to_unlink = lines_to_unlink.filtered(lambda l: l.date_from >= forced_recompute_date)
            lines_to_unlink.unlink()
        else:
            lines.filtered(lambda l: not l.has_confirmed_payslip).unlink()

        # Compute holiday usage per employee
        all_usage_employees = self.mapped('holiday_id.employee_id')

        all_employee_accumulations = HrEmployeeHolidayAccumulation.sudo().search([
            ('employee_id', 'in', all_usage_employees.ids)
        ])

        for employee in all_usage_employees:
            # Find usages that are recomputed for the employee
            employee_usages = self.filtered(lambda usage: usage.employee_id == employee)
            domain = [('holiday_id.employee_id', '=', employee.id)]
            if employee_usages:
                domain.append(('holiday_id.date_to_date_format', '>=', min(employee_usages.mapped('date_from'))))
            usages_to_recompute_for_employee = self.search(domain)
            existing_usage_lines = usages_to_recompute_for_employee.mapped('line_ids')
            if self._context.get('force_recompute_confirmed') or forced_recompute_date:
                if forced_recompute_date:
                    existing_usage_lines.filtered(lambda l: l.usage_id.date_from >= forced_recompute_date).unlink()
                else:
                    existing_usage_lines.unlink()
            else:
                existing_usage_lines.filtered(lambda l: not l.has_confirmed_payslip).unlink()

            # Find and sort employee holiday payment lines by contract start date and payment period date from
            employee_payment_lines = usages_to_recompute_for_employee.mapped('holiday_id.allocated_payment_line_ids')
            employee_payment_lines = employee_payment_lines.sorted(
                key=lambda l: (
                    l.holiday_id.date_from_date_format,
                    l.holiday_id.state != 'validate',  # This sorts by validate state first (the '!=' is confusing)
                    l.period_date_from,
                    l.holiday_id.contract_id.date_start,
                )
            )

            # Find employee accumulations
            employee_accumulations = all_employee_accumulations.filtered(
                lambda accumulation: accumulation.employee_id == employee
            ).sorted(key=lambda accumulation: accumulation.date_from)

            # When the holiday is not validated we still want to create lines that are assigned to accumulations but
            # they are only so to say placeholder lines that do not impact accumulation. When we get the accumulation
            # balance for each payment line - the full balance is returned and we want to take into account the balance
            # used by those theoretical lines.
            theoretically_used_accumulation_balances = {}

            # Create usage line records for each payment line
            for payment_line in employee_payment_lines:
                payment_usage_lines = existing_usage_lines.exists().filtered(
                    lambda usage_line: usage_line.holiday_payment_line_id == payment_line
                )

                payment_line_usage = usages_to_recompute_for_employee.filtered(
                    lambda usage: usage.holiday_id == payment_line.holiday_id
                )

                dates_from = [
                    self._context.get('min_date_from') or payment_line.period_date_from,
                    payment_line.holiday_id.contract_id.work_relation_start_date,
                    payment_line.period_date_from,
                ]

                # Adjust the accumulation start date
                holiday_accumulation_usage_start_date = employee.holiday_accumulation_usage_start_date
                if holiday_accumulation_usage_start_date:
                    holiday_accumulation_usage_start_date_dt = datetime.strptime(
                        holiday_accumulation_usage_start_date, tools.DEFAULT_SERVER_DATE_FORMAT
                    )
                    holiday_accumulation_usage_start_date_dt += relativedelta(days=1)
                    holiday_accumulation_usage_start_date = holiday_accumulation_usage_start_date_dt.strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT
                    )
                    dates_from.append(holiday_accumulation_usage_start_date)

                min_date_from = max(dates_from)
                max_date_to = min(
                    self._context.get('max_date_to') or payment_line.period_date_to,
                    payment_line.holiday_id.contract_id.work_relation_end_date or payment_line.period_date_to,
                    payment_line.period_date_to
                )

                if min_date_from > max_date_to:
                    continue

                current_payment_line_holiday_duration = payment_line_usage.with_context(
                    min_date_from=min_date_from, max_date_to=max_date_to
                ).current_holiday_duration
                holiday_days_to_assign = min(payment_line.num_work_days, current_payment_line_holiday_duration)
                # Some lines for the payment already exist so we need to calculate how many days we still need to assign
                if payment_usage_lines:
                    holiday_days_to_assign -= sum(payment_usage_lines.mapped('used_days'))

                if tools.float_compare(holiday_days_to_assign, 0.0, precision_digits=2) < 0:
                    continue

                usage_line_values = []

                # Loop through each employee accumulation record and create holiday usage lines
                for employee_accumulation in employee_accumulations:
                    # Break when the usage for all of the days of this holiday has been correctly set
                    if tools.float_is_zero(holiday_days_to_assign, precision_digits=2):
                        break

                    # Maximum days that can be used for the accumulation is the balance of days left
                    max_days_to_be_used = employee_accumulation.accumulation_work_day_balance

                    theoretically_used_days = theoretically_used_accumulation_balances.get(employee_accumulation.id, 0.0)
                    max_days_to_be_used -= theoretically_used_days

                    if tools.float_compare(max_days_to_be_used, 0.0, precision_digits=2) <= 0:
                        continue

                    payment_days_adjusted = holiday_days_to_assign

                    # Don't use more than available
                    used_days_for_accumulation = min(max_days_to_be_used, payment_days_adjusted)

                    # Deduct the days used so we get the amount of how many days we still have use
                    holiday_days_to_assign -= used_days_for_accumulation

                    # If the holiday is not validated the accumulation does not register the usage line as a proper
                    # usage line thus we need to keep track of the theoretically used days
                    if payment_line.holiday_id.state != 'validate':
                        total_theoretical_used_days = theoretically_used_days + used_days_for_accumulation
                        theoretically_used_accumulation_balances[employee_accumulation.id] = total_theoretical_used_days

                    # Accumulation payment usage line already exists so we should not be creating another line for it.
                    existing_accumulation_payment_usage_line = payment_usage_lines.filtered(
                        lambda l: l.used_accumulation_id == employee_accumulation
                    )
                    if existing_accumulation_payment_usage_line:
                        usage_line = existing_accumulation_payment_usage_line[0]
                        usage_line.write({'used_days': usage_line.used_days + used_days_for_accumulation})
                        continue

                    # Add to the list of usage line values
                    usage_line_values.append(
                        (0, 0, {
                            'usage_id': payment_line_usage.id,
                            'holiday_payment_line_id': payment_line.id,
                            'used_accumulation_id': employee_accumulation.id,
                            'used_days': used_days_for_accumulation,
                        })
                    )

                # Create the usage lines
                payment_line_usage.write({'line_ids': usage_line_values})

    @api.multi
    @api.depends('holiday_id.allocated_payment_line_ids.num_work_days', 'line_ids.used_days')
    def _compute_used_days(self):
        for rec in self:
            holiday = rec.holiday_id
            rec.used_days = sum(holiday.mapped('allocated_payment_line_ids.num_work_days'))
            rec.accumulation_assigned_days = sum(rec.line_ids.mapped('used_days'))

    @api.multi
    @api.depends('holiday_id', 'holiday_id.contract_id', 'holiday_id.date_from', 'holiday_id.date_to',
                 'line_ids.used_days')
    def _compute_current_holiday_duration(self):
        """
        Computes the amount of days that have impact from the holiday based on the contract dates and todays date
        """
        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        max_date_to = self._context.get('max_date_to') or now
        min_date_from = self._context.get('min_date_from')
        for rec in self:
            holiday = rec.holiday_id

            contract = holiday.sudo().contract_id
            if not contract:
                continue  # Should never be the case

            # Compute the period that's no later than today or the end of the work relation
            date_from, date_to = holiday.date_from_date_format, holiday.date_to_date_format
            if min_date_from:
                date_from = max(date_from, min_date_from)
            date_from = max(date_from, contract.work_relation_start_date)
            date_to = min(date_to, max_date_to, contract.work_relation_end_date or max_date_to)

            if date_from > date_to:
                continue  # Holiday has not yet started

            leave_days = 0.0

            appointments = contract.appointment_ids.filtered(
                lambda app: app.date_start <= date_to and (not app.date_end or app.date_end >= date_from)
            )
            for appointment in appointments:
                # Calculate appointment period for holiday
                app_period_start = max(appointment.date_start, date_from)
                app_period_end = min(
                    appointment.date_end or date_to,  # Appointments might not have end date
                    date_to
                )

                if app_period_start > app_period_end:
                    continue

                # Get number of work days
                schedule_template = appointment.schedule_template_id
                app_leave_days = schedule_template.with_context(
                    force_use_schedule_template=True, calculating_holidays=True
                ).num_work_days(app_period_start, app_period_end)

                if schedule_template.template_type not in ['fixed', 'suskaidytos']:
                    # Convert to work days since for other templates all days will be work days
                    app_leave_days *= schedule_template.num_week_work_days / 7.0  # P3:DivOK
                leave_days += app_leave_days

            rec.current_holiday_duration = leave_days

    @api.model
    def _update_holiday_accumulations_and_usages(self):
        # Update accumulation accumulated holiday days
        now = datetime.now()
        today = now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        three_months_ago = (now - relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        HrEmployeeHolidayAccumulation = self.env['hr.employee.holiday.accumulation']
        # Refresh the latest accumulations with appointments
        accumulations_to_refresh = HrEmployeeHolidayAccumulation.search([
            ('appointment_id', '!=', False),
            '|',
            ('date_to', '>=', today),
            ('date_to', '=', False)
        ])
        # Also refresh the accumulations of the last 3 months with appointment values that do not match
        other_accumulations = HrEmployeeHolidayAccumulation.search([
            ('appointment_id', '!=', False),
            ('appointment_id', 'not in', accumulations_to_refresh.mapped('appointment_id').ids),
            ('date_to', '>=', three_months_ago),
        ])
        for accumulation in other_accumulations:
            appointment = accumulation.appointment_id
            if accumulation.employee_id != appointment.employee_id or \
                accumulation.date_from != appointment.date_start or accumulation.date_to != appointment.date_end or \
                tools.float_compare(accumulation.post, appointment.schedule_template_id.etatas, precision_digits=2) != 0 or \
                accumulation.accumulation_type != appointment.leaves_accumulation_type:
                accumulations_to_refresh |= accumulation

        accumulations_to_refresh.with_context(recompute=False).set_appointment_values()

        # Create holiday usages for holidays without accumulation
        holidays_without_usages = self.env['hr.holidays'].search([
            ('date_from_date_format', '<=', today),
            ('holiday_status_id.kodas', '=', 'A'),
            ('holiday_usage_id', '=', False),
            ('holiday_accumulation_usage_policy', '=', True)
        ]).filtered(lambda h: h.should_have_a_usage_record)
        holidays_without_usages.create_and_recompute_holiday_usage()

        # Update all ongoing holiday usages
        self.search([('holiday_id.date_to_date_format', '>=', today)])._recompute_holiday_usage()
