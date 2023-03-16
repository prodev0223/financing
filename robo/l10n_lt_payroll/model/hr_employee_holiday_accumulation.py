# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class HrEmployeeHolidayAccumulation(models.Model):
    _name = 'hr.employee.holiday.accumulation'
    _inherit = 'mail.thread'

    appointment_id = fields.Many2one('hr.contract.appointment', string='Appointment', required=False,
                                     ondelete='set null', inverse='_recompute_holiday_usage')
    employee_id = fields.Many2one('hr.employee', string='Employee', store=True,
                                  readonly=False, ondelete='cascade', track_visibility='onchange',
                                  inverse='_recompute_holiday_usage', required=True)
    date_from = fields.Date(string='Date from', readonly=False, store=True,
                            track_visibility='onchange', inverse='_recompute_holiday_usage', required=True)
    date_to = fields.Date(string='Date to', readonly=False, store=True,
                          track_visibility='onchange', inverse='_recompute_holiday_usage')
    post = fields.Float(string='Post', readonly=False,
                        store=True, track_visibility='onchange', required=True)
    accumulated_days = fields.Float(string='Accumulated holiday days', readonly=False, store=True,
                                    track_visibility='onchange', inverse='_recompute_holiday_usage')
    compensated_days = fields.Float(string='Compensated days',
                                    help='Days compensated for working overtime or on free days',
                                    compute='_compute_compensated_days')
    used_days_by_holidays = fields.Float(string='Used holiday days (from holiday records)',
                                         compute='_compute_used_days_by_holidays', inverse='_recompute_holiday_usage',
                                         readonly=True)
    used_days_from_other = fields.Float(string='Additionally used days (set manually)', default=0.0,
                                        track_visibility='onchange', inverse='_recompute_holiday_usage')
    used_days_total = fields.Float(string='Total used days',
                                   compute='_compute_total_used_days_and_accumulation_balance')
    accumulation_balance = fields.Float(string='Accumulated days left',
                                        compute='_compute_total_used_days_and_accumulation_balance')
    num_leaves_per_year = fields.Float(inverse='_recompute_holiday_usage')
    accumulation_type = fields.Selection(
        [
            ('work_days', 'Work days'),
            ('calendar_days', 'Calendar days')
        ], string='Accumulation type', track_visibility='onchange',
        inverse='_recompute_holiday_usage', store=True,
        required=True
    )
    holiday_usage_line_ids = fields.One2many('hr.employee.holiday.usage.line', 'used_accumulation_id',
                                             string='Holiday usage', domain=[('confirmed', '=', True)])
    accumulation_work_day_balance = fields.Float(string='Accumulated work days left',
                                                 compute='_compute_accumulation_work_day_balance')

    @api.multi
    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_compensated_days(self):
        holiday_compensations = self.env['hr.employee.holiday.compensation'].sudo().search([
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('state', '=', 'confirmed'),
            ('date', '>=', min(self.mapped('date_from'))),
        ])
        forced_date_to = self._context.get('date_to')
        for rec in self:
            date_to = forced_date_to or rec.date_to or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_to < rec.date_from:
                rec.compensated_days = 0.0
                continue
            holiday_compensations_for_accumulation = holiday_compensations.filtered(
                lambda c: c.employee_id == rec.employee_id and rec.date_from <= c.date <= date_to
            )
            work_days_compensated = sum(holiday_compensations_for_accumulation.mapped('number_of_days'))
            if rec.accumulation_type == 'work_days':
                rec.compensated_days = work_days_compensated
            else:
                rec.compensated_days = work_days_compensated * 7.0 / 5.0  # P3:DivOK

    @api.multi
    @api.depends('accumulated_days', 'used_days_from_other', 'employee_id', 'date_from', 'date_to',
                 'holiday_usage_line_ids.used_days', 'holiday_usage_line_ids.confirmed', 'accumulation_type',
                 'appointment_id.schedule_template_id')
    def _compute_accumulation_work_day_balance(self):
        for rec in self:
            date = self._context.get('forced_date_to')
            accumulation_balance = rec.get_balance_before_date(date) if date else rec.accumulation_balance

            if rec.accumulation_type == 'work_days':
                rec.accumulation_work_day_balance = accumulation_balance
            else:
                appointment = rec.appointment_id
                num_week_work_days = appointment.schedule_template_id.num_week_work_days if appointment else 5.0
                rec.accumulation_work_day_balance = accumulation_balance * num_week_work_days / 7.0  # P3:DivOK

    @api.multi
    def name_get(self):
        res = []
        for accumulation in self:
            name = _('{} holiday accumulation from {}').format(accumulation.employee_id.name, accumulation.date_from)
            if accumulation.date_to:
                name += _(' to {}').format(accumulation.date_to)
            res.append((accumulation.id, name))
        return res

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_date_from_less_than_date_to(self):
        for rec in self:
            if rec.date_to and rec.date_to < rec.date_from:
                raise exceptions.UserError(_('Date from has to be less than date to'))

    @api.multi
    @api.constrains('appointment_id', 'employee_id', 'date_from', 'date_to')
    def _check_single_record_for_single_period(self):
        for rec in self.filtered(lambda r: not r.appointment_id):
            domain = [
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                '|',
                ('date_to', '=', False),
                ('date_to', '>=', rec.date_from)
            ]
            if rec.date_to:
                domain.append(('date_from', '<=', rec.date_to))
            other_records = self.search_count(domain)
            if other_records:
                msg = _('A record for {} in period from {}').format(rec.employee_id.name, rec.date_from)
                if rec.date_to:
                    msg += _(' to {}').format(rec.date_to)
                msg += _(' already exists. Please modify the existing record or choose different dates')
                raise exceptions.Warning(msg)

    @api.multi
    @api.constrains('appointment_id')
    def _check_single_record_for_single_appointment(self):
        for rec in self.filtered(lambda r: r.appointment_id):
            other_recs = self.search_count([
                ('id', '!=', rec.id),
                ('appointment_id', '=', rec.appointment_id.id)
            ])
            if other_recs:
                raise exceptions.UserError(_('A record for this appointment already exists. Can not have multiple '
                                             'holiday accumulation records for one appointment'))

    @api.multi
    @api.constrains('accumulated_days')
    def _check_accumulated_days_positive(self):
        for rec in self:
            if tools.float_compare(rec.accumulated_days, 0.0, precision_digits=2) < 0 and not rec.appointment_id:
                raise exceptions.UserError(_('Accumulated days must be more than zero'))

    @api.multi
    def set_appointment_values(self):
        for rec in self.filtered(lambda r: r.appointment_id):
            app = rec.appointment_id
            rec.write({
                'employee_id': app.employee_id.id,
                'date_from': app.date_start,
                'date_to': app.date_end,
                'post': app.schedule_template_id.etatas,
                'accumulation_type': app.leaves_accumulation_type,
                'accumulated_days': app.accumulated_holiday_days,
            })

    @api.multi
    @api.onchange('appointment_id')
    def _onchange_appointment_set_appointment_values(self):
        for rec in self.filtered(lambda r: r.appointment_id):
            app = rec.appointment_id
            rec.employee_id = app.employee_id.id
            rec.date_from = app.date_start
            rec.date_to = app.date_end
            rec.post = app.schedule_template_id.etatas
            rec.accumulation_type = app.leaves_accumulation_type
            rec.accumulated_days = app.accumulated_holiday_days

    @api.multi
    @api.constrains('post')
    def _check_post_value(self):
        if any(
            tools.float_compare(0.0, rec.post, precision_digits=3) >= 0 or
            tools.float_compare(2.0, rec.post, precision_digits=3) < 0
            for rec in self
        ):
            raise exceptions.UserError(_('Employee post has to be between 0.0 and 2.0'))

    @api.multi
    def unlink(self):
        if any(rec.appointment_id for rec in self) and not self._context.get('bypass_appointments') and \
                not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('''Some entries you're trying to unlink have a related appointment and 
            therefore can not be deleted'''))
        return super(HrEmployeeHolidayAccumulation, self).unlink()

    @api.multi
    @api.depends('holiday_usage_line_ids.used_days', 'holiday_usage_line_ids.confirmed')
    def _compute_used_days_by_holidays(self):
        date_to = self._context.get('date_to')  # Allow forcing a date to which the days used by holidays are calculated
        for rec in self:
            usage_lines = rec.holiday_usage_line_ids.filtered(lambda l: l.confirmed)
            days_used_after = 0.0
            if date_to:
                # Find lines in between to process
                lines_in_between = usage_lines.filtered(lambda l: l.date_from <= date_to <= l.date_to)
                # Filter all lines that are before or on the date
                usage_lines = usage_lines.filtered(lambda l: l.date_from <= date_to)

                for line in lines_in_between:
                    # Compute basic attributes
                    accumulation_type = line.holiday_id.leaves_accumulation_type
                    six_day_work_week = rec.appointment_id and \
                                        rec.appointment_id.schedule_template_id.work_week_type == 'six_day'

                    if accumulation_type == 'calendar_days':
                        # Days used after date will be the calendar days after converted to work days by proportion
                        date_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                        date_to_dt = datetime.strptime(line.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                        period_after = (date_to_dt - date_dt).days
                        num_week_work_days = 6.0 if six_day_work_week else 5.0
                        days_used_after += period_after / 7.0 * num_week_work_days  # P3:DivOK
                    else:
                        # Days used after will be the regular work days for that period
                        days_used_after += self.env['hr.payroll'].sudo().standard_work_time_period_data(
                            date_to,
                            line.date_to,
                            six_day_work_week=six_day_work_week
                        ).get('days', 0.0)

            # Used days by holidays are used days by usage lines minus the days that will be used after
            rec.used_days_by_holidays = sum(usage_lines.mapped('used_days')) - days_used_after

    @api.multi
    @api.depends('accumulated_days', 'used_days_from_other', 'employee_id', 'date_from', 'date_to',
                 'holiday_usage_line_ids.used_days', 'holiday_usage_line_ids.confirmed', 'accumulation_type')
    def _compute_total_used_days_and_accumulation_balance(self):
        for rec in self:
            total_used = rec.used_days_by_holidays + rec.used_days_from_other
            if rec.accumulation_type == 'calendar_days':
                appointment = rec.appointment_id
                num_week_work_days = appointment.schedule_template_id.num_week_work_days if appointment else 5.0
                try:
                    total_used = total_used * 7.0 / num_week_work_days  # P3:DivOK
                except:
                    total_used = total_used
            rec.used_days_total = total_used
            rec.accumulation_balance = rec.accumulated_days - total_used + rec.compensated_days

    @api.multi
    def recalculate_accumulated_holiday_days(self):
        self.ensure_one()
        if self.appointment_id:
            self.write({'accumulated_days': self.appointment_id.accumulated_holiday_days})

    @api.multi
    def get_balance_before_date(self, date):
        balance = 0.0
        today_dt = datetime.utcnow()
        today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        tomorrow = (today_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            if date < rec.date_from:
                continue  # Don't add balance since getting for date before accumulation

            date_to = rec.date_to or today

            if date > date_to or (not rec.date_to and date == tomorrow):
                # Add the actual accumulation balance since the accumulation record is in the period before the date
                # requested
                balance += rec.with_context(date_to=date).accumulation_balance
                continue

            # Calculate leaves accumulated after date
            if not rec.appointment_id:
                leaves_per_year = rec.total_leaves_per_year or \
                                  self.env['hr.holidays'].sudo().get_employee_default_holiday_amount(
                                      job_id=rec.employee_id.job_id, employee_dob=rec.employee_id.birthday)

                date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

                if rec.accumulation_type == 'calendar_days':
                    if not rec.total_leaves_per_year:
                        # get_employee_default_holiday_amount will return work days
                        leaves_per_year = leaves_per_year * 7.0 / 5.0  # P3:DivOK

                    # Get number of leaves per day
                    days_per_year = (datetime(date_dt.year + 1, 1, 1) - datetime(date_dt.year, 1, 1)).days
                    leaves_per_day = leaves_per_year / days_per_year  # P3:DivOK

                    # Get number of calendar days after the requested date for the accumulation record
                    days_after = (date_to_dt - date_dt).days
                else:
                    year_start = (date_dt + relativedelta(day=1, month=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    next_year_start = (date_dt + relativedelta(day=1, month=1, years=1)).strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT)
                    work_days_per_year = self.env['hr.payroll'].sudo().standard_work_time_period_data(
                        year_start,
                        next_year_start
                    ).get('days', 0.0)

                    try:
                        leaves_per_day = leaves_per_year / work_days_per_year  # P3:DivOK
                    except ZeroDivisionError:
                        leaves_per_day = 0.0

                    days_after = self.env['hr.payroll'].sudo().standard_work_time_period_data(date, date_to, ).get(
                        'days', 0.0
                    )
                accumulated_days = rec.accumulated_days - leaves_per_day * days_after
            else:
                accumulated_days = rec.appointment_id.with_context(forced_date_to=date)._get_accumulated_holiday_days()

            # Calculate the total number of days used before the holiday
            total_used = rec.with_context(date_to=date).used_days_by_holidays + rec.used_days_from_other
            if rec.accumulation_type == 'calendar_days':
                # Adjust total used days to calendar days
                appointment = rec.appointment_id
                num_week_work_days = appointment.schedule_template_id.num_week_work_days if appointment else 5.0
                try:
                    total_used = total_used * 7.0 / num_week_work_days  # P3:DivOK
                except ZeroDivisionError as e:
                    pass
            compensated_days_after_date = rec.with_context(date_to=date_to).compensated_days
            adjustment_balance = accumulated_days - total_used + rec.compensated_days - compensated_days_after_date
            balance += adjustment_balance
        return round(balance, 3)

    @api.multi
    def _recompute_holiday_usage(self):
        self.env['hr.employee.holiday.usage'].sudo().search([
            ('employee_id', 'in', self.mapped('employee_id').ids)
        ])._recompute_holiday_usage()

    @api.model
    def recreate_holiday_accumulations(self, employees=None):
        if employees:
            existing_accumulations = self.search([('employee_id', 'in', employees.ids)])
            existing_usages = self.env['hr.employee.holiday.usage'].search([('employee_id', 'in', employees.ids)])
        else:
            existing_accumulations = self.search([])
            existing_usages = self.env['hr.employee.holiday.usage'].search([])
        existing_accumulations.sudo().with_context(bypass_appointments=True).unlink()
        existing_usages.sudo().unlink()

        domain = [('employee_id.type', '!=', 'intern'), ('type', '=', 'set')]
        if employees:
            domain.append(('employee_id', 'in', employees.ids))
        holiday_fixes = self.env['hr.holidays.fix'].search(domain)
        if not employees:
            employees = holiday_fixes.mapped('employee_id')
        appointments = self.env['hr.contract.appointment'].search([('employee_id', 'in', employees.ids)])

        hr_holidays = self.env['hr.holidays'].search([
            ('employee_id', 'in', employees.ids),
            ('state', '=', 'validate'),
            ('holiday_status_id.kodas', '=', 'A')
        ])

        for employee in employees:
            # Find appointments for the employee
            employee_appointments = appointments.filtered(lambda app: app.employee_id == employee)
            last_appointment = employee_appointments and \
                               employee_appointments.sorted(key=lambda app: app.date_start, reverse=True)[0]
            last_contract = last_appointment.contract_id if last_appointment else None

            # Find last holiday fix
            employee_holiday_fixes = holiday_fixes.filtered(lambda fix: fix.employee_id == employee)
            if last_contract and last_contract.work_relation_end_date:
                # Make sure the last fix is not the fix that gets created when the employee is let go
                employee_holiday_fixes = employee_holiday_fixes.filtered(
                    lambda fix: fix.date < last_contract.work_relation_end_date
                )
            employee_holiday_fixes = employee_holiday_fixes.sorted(key=lambda fix: fix.date, reverse=True)
            last_holiday_fix = employee_holiday_fixes and employee_holiday_fixes[0]

            employee_holidays = hr_holidays.filtered(lambda holiday: holiday.employee_id == employee)

            min_date_from = None
            if last_holiday_fix:
                # Find appointments valid during or after last fix
                employee_appointments = employee_appointments.filtered(
                    lambda app: not app.date_end or app.date_end >= last_holiday_fix.date
                )
                now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                employee_holidays = employee_holidays.filtered(
                    lambda holiday: holiday.date_to_date_format >= last_holiday_fix.date and
                                    holiday.date_from_date_format <= now
                )
                fix_date_dt = datetime.strptime(last_holiday_fix.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                min_date_from = (fix_date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            if not employee_appointments:
                continue

            employee_appointments = employee_appointments.sorted(key=lambda app: app.date_start)
            employee_appointments._create_holiday_accumulation_records()

            # Filtered by holiday type inside the holiday usage creation method
            # Recompute with each appointment after accumulation record has been created so that the available
            # balance is "filled"
            employee_holidays.with_context(min_date_from=min_date_from).create_and_recompute_holiday_usage()
