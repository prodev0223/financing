# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    appointment_ids = fields.One2many('hr.contract.appointment', 'employee_id', string='Priedai',
                                      groups="hr_payroll.group_hr_payroll_user",
                                      )
    appointment_id = fields.Many2one('hr.contract.appointment', compute='_appointment_id', string='Priedas',
                                     help='Nurodytos datos priedas arba paskutinis galiojęs', sequence=100)

    holiday_coefficient = fields.Float(
        string="Holiday coefficient",
        help="Coefficient that is applied when calculating holidays payments. Usually used while there's no info of "
             "employee post changes for periods before migrating accounting to Robo.",
        groups="hr_payroll.group_hr_payroll_user",
        default=1.0,
        required=False,
        track_visibility='onchange'
    )
    holiday_accumulation_usage_policy = fields.Boolean(
        string='Use holiday accumulation and usage records when calculating holiday payments',
        groups='hr.group_hr_manager'
    )
    is_absent = fields.Boolean(compute='_compute_is_absent')
    holiday_accumulation_usage_start_date = fields.Date(compute='_compute_holiday_accumulation_usage_start_date')

    @api.multi
    def _compute_is_absent(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            return
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        holidays = self.env['hr.holidays'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', 'in', self.ids),
            ('date_from_date_format', '<=', date),
            ('date_to_date_format', '>=', date),
            ('holiday_status_id.kodas', '!=', 'K')
        ])
        employees_on_holidays = holidays.mapped('employee_id')
        for rec in self:
            rec.is_absent = rec in employees_on_holidays

    @api.multi
    @api.depends()
    def _compute_holiday_accumulation_usage_start_date(self):
        # Find all related holiday accumulations
        holiday_accumulations = self.env['hr.employee.holiday.accumulation'].search([
            ('employee_id', 'in', self.ids)
        ])

        # Find all related holiday fixes
        holiday_fixes = self.env['hr.holidays.fix'].search([
            ('employee_id', 'in', self.ids),
            ('type', '=', 'set'),
        ])

        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        for employee in self:
            # Find earliest holiday accumulation for each employee
            employee_accumulations = holiday_accumulations.filtered(
                lambda a: a.employee_id == employee
            ).sorted(key=lambda acc: acc.date_from)
            earliest_accumulation = employee_accumulations and employee_accumulations[0]
            if not earliest_accumulation:
                continue

            # Determine the dates of the earliest accumulation.
            date_from = earliest_accumulation.date_from
            date_to = earliest_accumulation.date_to or today  # Might still be accumulating as of today

            # Find the last holiday fix for the first accumulation.
            employee_holiday_fixes = holiday_fixes.filtered(
                lambda fix: fix.employee_id == employee and date_from <= fix.date <= date_to
            ).sorted(key=lambda fix: fix.date, reverse=True)
            last_holiday_fix = employee_holiday_fixes and employee_holiday_fixes[0]
            if last_holiday_fix:
                date_from = max(date_from, last_holiday_fix.date)

            employee.holiday_accumulation_usage_start_date = date_from

    @api.one
    def _appointment_id(self):
        date = self._context.get('date') or datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if type(self.id) == int:
            self._cr.execute('''select id from hr_contract_appointment
                                        where employee_id = %s
                                        AND date_start <= %s
                                        ORDER BY date_start desc
                                        limit 1''', (self.id, date))
            res = self._cr.fetchall()
            if res and res[0]:
                self.appointment_id = res[0][0]
            else:
                self.appointment_id = False

    @api.multi
    def open_contract_create_wizard(self):
        self.ensure_one()
        context = {'active_id': self.id}
        if self.department_id:
            context.update({'default_department_id': self.department_id.id})
        if self.job_id:
            context.update({'default_job_id': self.job_id.id})
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.contract.create',
            'view_id': False,
            'target': 'new',
            'context': context,
        }

    @api.constrains('company_id')
    def constrain_company(self):
        for rec in self:
            if not rec.company_id:
                raise exceptions.ValidationError(_('Darbuotojas nėra priskirtas įmonei.'))

    @api.model
    def get_active_employee(self, date_from, date_to):
        return self.env['hr.contract'].search([('date_start', '<=', date_to),
                                               '|',
                                                    ('date_end', '=', False),
                                                    ('date_end', '>=', date_from)]).mapped('employee_id.id')

    @api.multi
    def _get_gender_from_identification_id(self):
        """
        Gets the gender from the identification id
        """
        self.ensure_one()
        if not self.identification_id or self.is_non_resident:
            return None
        gender_identifier = self.identification_id[0]
        try:
            gender_identifier = int(gender_identifier)
        except ValueError:
            gender_identifier = None
        if gender_identifier in [1, 3, 5]:
            return 'male'
        elif gender_identifier in [2, 4, 6]:
            return 'female'
        return None

    @api.multi
    @api.onchange('identification_id', 'gender')
    def _onchange_identification_id(self):
        """
        Sets the employee gender based on the identification id. Skips employees who are non residents or don't have an
        identification id
        """

        for rec in self:
            gender = rec._get_gender_from_identification_id()
            if gender and not rec.gender:
                rec.gender = gender

    @api.multi
    @api.constrains('identification_id', 'gender')
    def _check_gender(self):
        """
        Checks that the employee gender is correctly set based on the identification id.
        """
        gender_selectors = dict(self.sudo()._fields.get('gender', False)._description_selection(self.env))
        for rec in self:
            gender = rec._get_gender_from_identification_id()
            if gender and rec.gender and rec.gender != gender:
                raise exceptions.UserError(_('Darbuotojo {} lytis nustatyta, kaip {}, tačiau pagal asmens kodą šio '
                                             'darbuotojo lytis turėtų būti {}.').format(
                    rec.name, gender_selectors.get(rec.gender), gender_selectors.get(gender)
                ))

    @api.multi
    def inform_accountant_about_work_relation_end_with_delegate_or_department_manager(self):
        """
        If work relations with a delegate or department manager are over or the employee is archived,
        send a ticket to accountant informing about the need to appoint a new delegate or manager
        """
        self.ensure_one()
        positions = self.get_information_for_ticket()
        if positions:
            subject = _('Work relation with a delegate or department manager has ended, '
                        'appoint a new one to the vacant positions')
            body = _('Work relation with {} has ended or he has been archived. The employee was: \n{};'
                     '\nDo not forget to appoint a new employee for the vacant positions.').format(
                self.name_related, ';\n'.join(positions))
            try:
                ticket_obj = self.sudo()._get_ticket_rpc_object()
                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'name': subject,
                    'description': body,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name,
                }
                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError('The distant method did not create the ticket.')
            except Exception as exc:
                message = 'Failed to create ticket informing the accountant about the need to replace a delegate or ' \
                          'department manager after work relation end. ' \
                          '\nTicket:{}\nException: {}'.format(body, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def get_information_for_ticket(self):
        """ Returns a list of employee positions for the ticket if employee is a delegate or head of department """
        self.ensure_one()
        positions = []
        managed_departments = self.env['hr.department'].search([('manager_id', '=', self.id)]).mapped('name')
        if managed_departments:
            positions.append(_('Head of following departments: {}').format(', '.join(managed_departments)))

        return positions

    @api.multi
    def get_worked_time(self, date_from, date_to):
        """
        Gets worked time for specific employees for specified date range
        @param date_from: (str) Date from to get the work time for
        @param date_to: (str) Date to to get the work time for
        """
        worked_time_codes = PAYROLL_CODES['WORKED'] + PAYROLL_CODES['OUT_OF_OFFICE'] + \
                            PAYROLL_CODES['UNPAID_OUT_OF_OFFICE'] + PAYROLL_CODES['DOWNTIME']

        # Get timesheet (ziniarastis) days
        timesheet_days = self.env['ziniarastis.day'].search([
            ('employee_id', 'in', self.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to)
        ])
        data = {}
        for employee in timesheet_days.mapped('employee_id'):
            # Add data to totals dict
            employee_days = timesheet_days.filtered(lambda d: d.employee_id == employee)
            day_lines = employee_days.mapped('ziniarastis_day_lines').filtered(lambda l: l.code in worked_time_codes)
            data[employee.id] = {
                'worked_time': sum(day_lines.mapped('total_worked_time_in_hours')),
                'is_preliminary': any(
                    line.state != 'done' for line in employee_days.mapped('ziniarastis_period_line_id')
                )
            }
        return data

    @api.multi
    def get_minimum_wage_for_date(self, mma_date, period_date=None):
        """
        Calculates the minimum daily wage and the minimum hourly wage for the employee for the given date
        @param mma_date: (str) Minimum wage calculation date
        @param period_date: (str) Period date
        @return: (dict) {'day': Minimum daily wage, 'hour': Minimum hourly wage}
        """

        if len(self) > 1:
            self.ensure_one()  # Only allow empty hr.employee or a single hr.employee

        if not period_date:
            period_date = mma_date  # Period is the same as the minimum wage date

        date_format = tools.DEFAULT_SERVER_DATE_FORMAT
        datetime_format = tools.DEFAULT_SERVER_DATETIME_FORMAT

        # Compute period
        try:
            period_date_dt = datetime.strptime(period_date, date_format)
        except ValueError:
            period_date_dt = datetime.strptime(period_date, datetime_format)
        date_from_dt = period_date_dt + relativedelta(day=1)
        date_to_dt = period_date_dt + relativedelta(day=31)
        date_from, date_to = date_from_dt.strftime(date_format), date_to_dt.strftime(date_format)

        company = self.env.user.company_id

        minimum_hourly_wage = company.with_context(date=mma_date).min_hourly_rate

        # Get contract data
        if len(self) == 1:
            appointment = self.with_context(date=mma_date).appointment_id
        else:
            appointment = self.env['hr.contract.appointment']
        schedule_template = appointment.schedule_template_id
        contract = appointment.contract_id

        # Get standard data
        standard_work_time_period_data = self.env['hr.payroll'].standard_work_time_period_data(date_from, date_to)
        num_regular_work_days = standard_work_time_period_data.get('days', 0.0)
        minimum_wage = company.with_context(date=mma_date).mma
        post = work_norm = 1.0

        if contract:
            # Get minimum wage and number of regular work days from contract
            minimum_wage = contract.with_context(date=mma_date).get_payroll_tax_rates(['mma'])['mma']
            appointment_regular_work_days = appointment.with_prefetch().with_context(date=date_from, maximum=True).num_regular_work_days
            if tools.float_compare(appointment_regular_work_days, 0.0, precision_digits=2) > 0:
                num_regular_work_days = appointment_regular_work_days
                post, work_norm = schedule_template.etatas, schedule_template.work_norm

        num_regular_work_days = max(num_regular_work_days, 0.0)  # Should never be negative

        # Calculate the minimum hourly wage based on the minimum daily wage
        try:
            minimum_daily_wage = minimum_wage * post / num_regular_work_days  # P3:DivOK
        except ZeroDivisionError:
            minimum_daily_wage = 0.0
        hourly_wage_by_minimum_daily_wage = minimum_daily_wage / 8.0 * work_norm  # P3:DivOK

        # Ensure that the minimum hourly wage is not less than the hourly rate calculated based on the daily wage
        if tools.float_compare(minimum_hourly_wage, hourly_wage_by_minimum_daily_wage, precision_digits=2) < 0:
            minimum_hourly_wage = hourly_wage_by_minimum_daily_wage

        # Accumulative work time accounting - minimum hourly wage is calculated by weeks
        if schedule_template and schedule_template.template_type == 'sumine':
            calendar_days_for_period = (date_to_dt - date_from_dt).days + 1
            number_of_weeks = calendar_days_for_period / 7.0  # P3:DivOK
            monthly_work_hours = number_of_weeks * 40.0 * schedule_template.work_norm
            minimum_hourly_wage_based_on_weeks = minimum_wage / monthly_work_hours  # P3:DivOK
            hours_per_day = 8.0 * schedule_template.etatas * schedule_template.work_norm
            minimum_daily_wage_based_on_weeks = minimum_hourly_wage_based_on_weeks * hours_per_day
            minimum_hourly_wage = minimum_hourly_wage_based_on_weeks
            minimum_daily_wage = minimum_daily_wage_based_on_weeks

        return {'day': minimum_daily_wage, 'hour': minimum_hourly_wage}

    @api.multi
    def child_support_free_days_left(self, year, month):
        """
        @param year: year of the requested period
        @param month: month of the requested period
        @return int - returns the number of free days
        """
        self.ensure_one()
        date_dt = datetime(year, month, 1)
        date_from_str = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_str = (date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        allowed_days = self.sudo().get_allowed_free_child_support_free_days_amount(date_from_str)
        holidays = sum(self.env['hr.holidays'].sudo().search([
            ('employee_id', '=', self.id),
            ('date_from_date_format', '<=', date_to_str),
            ('date_to_date_format', '>=', date_from_str),
            ('state', '=', 'validate'),
            ('type', '=', 'remove'),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_M').id)
        ]).mapped('number_of_days'))
        free_days = allowed_days - holidays
        return free_days


HrEmployee()
