# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _

# Should be sorted lowest to highest ranking
SCHEDULE_STATES = [('draft', _('Juodraštis')),
                   ('validated', _('Patvirtinta')),
                   ('confirmed', _('Pateikta buhalterijai')),
                   ('done', _('Priimta'))]


def execute_multiple_insert_query(self, table_name, values):
    """Creates and executes an insert query into a table
        Returns the list of ids created
    """
    id_seq_string = 'nextval(\'%s_id_seq\')' % table_name

    # Safety checks
    self.check_access_rule('create')
    if not table_name or not values:
        return list()
    val_length = False
    for val in values:
        if not val_length:
            val_length = len(val)
        elif val_length != len(val) or len(val) == 0:
            raise exceptions.Warning(
                _('Nenumatyta sistemos klaida sukuriant duomenis. Kreipkitės į sistemos administratorių.'))

    query = 'INSERT INTO \"%s\" ("id", "create_date", "write_date", "create_uid", "write_uid", \"%s\") VALUES '
    field_names = list(values[0].keys())
    query = query % (table_name, "\",\"".join(field_names))

    values_list = list()
    id_seq_start_string = "(%s, (now() at time zone \'UTC\'), (now() at time zone \'UTC\'), %s, %s, " % (
    id_seq_string, self.env.user.id, self.env.user.id)
    i = 0
    for val_dict in values:
        query += id_seq_start_string
        for j in range(0, len(val_dict)):
            query += '%s'
            values_list.append(val_dict[field_names[j]])
            if j != (len(val_dict) - 1):
                query += ', '
        query += ')'
        if i != (len(values) - 1):
            query += ', '
        i += 1
    query += " RETURNING id;"
    self.env.cr.execute(query, values_list)
    ids_fetch = self.env.cr.dictfetchall()
    return [single_id['id'] for single_id in ids_fetch]


class WorkSchedule(models.Model):
    _name = 'work.schedule'

    def _default_company_id(self):
        return self.env.ref('base.main_company')

    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=_default_company_id,
                                 ondelete='cascade')
    name = fields.Char('Pavadinimas', default=_('Naujas Grafikas'), required=True)
    schedule_type = fields.Selection([('planned', _('Suplanuotas')),
                                      ('factual', _('Faktinis')),
                                      ('other', _('Kitas'))],
                                     string='Grafiko tipas', required=True)
    schedule_line_ids = fields.One2many('work.schedule.line', 'work_schedule_id', string='Grafiko eilutės')

    @api.multi
    @api.constrains('schedule_type')
    def _check_single_factual_and_main_schedule_per_company(self):
        for rec in self:
            if rec.schedule_type != 'other':
                num_of_other_same_type_schedules = self.search_count([
                    ('company_id', '=', rec.company_id.id),
                    ('schedule_type', '=', rec.schedule_type),
                    ('id', '!=', rec.id)
                ])
                if num_of_other_same_type_schedules != 0:
                    raise exceptions.UserError(_('Jau egzistuoja %s grafikas šiai kompanijai') % rec.schedule_type)

    @api.one
    def create_empty_schedule(self, year, month, employee_ids, department_ids, bypass_validated_time_sheets=False):
        """
        Creates an empty schedule for a specific year, month, employee and department based on regular schedule
        template values
        Args:
            year (int): year to create for
            month (int): month to create for
            employee_ids (list): employee_ids to create for
            department_ids (list): department_ids to create for
            bypass_validated_time_sheets (bool): allow adding lines even if time sheets have been validated
        """

        user = self.env.user

        # Check if the user is allowed to add lines to the requested department
        if not self.env.user.is_schedule_super():
            allow_adding = user.can_modify_schedule_departments(department_ids)
            if not allow_adding and user.is_schedule_manager():
                manager_department_ids = user.employee_ids.mapped('department_id').ids
                allow_adding = any(department_id not in manager_department_ids for department_id in department_ids)
            if not allow_adding:
                raise exceptions.ValidationError(_('Negalite pridėti eilutės į skyrių, kurio jūs neadministruojate.'))

        # Parse date
        date_from_dt = datetime(year, month, 1)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = date_from_dt + relativedelta(day=31)
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Check if time sheets have been validated already
        time_sheets_have_been_validated = self.sudo().env['ziniarastis.period'].search_count([
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('state', '=', 'done')
        ])
        if time_sheets_have_been_validated and not bypass_validated_time_sheets:
            error_message = _('Šio periodo žiniaraštis jau patvirtintas, pridėti eilučių nebegalima.')
            if self.env.user.has_group('robo_basic.group_robo_premium_accountant'):
                error_message += _('Norėdami pridėti eilutę - nueikite į darbo laiko apskaitos žiniaraštį ir '
                                   'paspauskite mygtuką "Atstatyti į juodraštį". Šis veiksmas neatšauks jau patvirtintų'
                                   ' žiniaraščių.')
            raise exceptions.UserError(error_message)

        # Check if the payroll is not busy
        payroll_is_busy = self.env['hr.payroll'].sudo().search_count([
            ('year', '=', year),
            ('month', '=', month),
            ('busy', '=', True)
        ])
        if payroll_is_busy and not self._context.get('automatic_payroll', False):
            raise exceptions.ValidationError(_('Negalite atlikti šio veiksmo, nes vykdomas atlyginimų skaičiavimas'))

        work_schedule_line_values = []
        existing_work_schedule_line_ids = self.env['work.schedule.line'].search([
            ('employee_id', 'in', employee_ids),
            ('department_id', 'in', department_ids),
            ('month', '=', month),
            ('year', '=', year),
            ('work_schedule_id', '=', self.id)
        ])

        # Build up a list of work schedule line values to create
        for employee_id in set(employee_ids):
            employee_lines = existing_work_schedule_line_ids.filtered(lambda l: l.employee_id.id == employee_id)
            for department_id in set(department_ids):
                existing_line = employee_lines.filtered(lambda l: l.department_id.id == department_id)
                if not existing_line:
                    work_schedule_line_values.append({
                        'work_schedule_id': self.id,
                        'employee_id': employee_id,
                        'department_id': department_id,
                        'year': year,
                        'month': month,
                        'state': 'draft'
                    })

        # Create new schedule lines
        work_schedule_line_ids = execute_multiple_insert_query(self, "work_schedule_line", work_schedule_line_values)
        work_schedule_lines = self.env['work.schedule.line'].browse(work_schedule_line_ids)

        # Build up a list of work schedule day values to create
        dates_of_month = [
            datetime(day=day, month=month, year=year).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for day in range(1, date_to_dt.day + 1)
        ]
        work_schedule_day_values = [{
            'work_schedule_line_id': line.id,
            'date': day_string,
            'business_trip': False,
            'free_day': False,
        } for day_string in dates_of_month for line in work_schedule_lines]

        # Create work schedule days from values and set default schedule day values if needed
        ids = execute_multiple_insert_query(self, "work_schedule_day", work_schedule_day_values)
        if self._context.get('do_not_fill_schedule'):
            return

        # Fill work schedule days from schedule template
        new_recs = self.env['work.schedule.day'].browse(ids)
        if new_recs:
            new_recs.set_default_schedule_day_values()

    @api.one
    def copy_to_schedule(self, schedule_to_copy_to, employee_id=False, department_id=False, dates=False):
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        is_planned_schedule = schedule_to_copy_to.id == planned_work_schedule.id
        lines = self.schedule_line_ids
        if employee_id:
            lines = lines.filtered(lambda l: l.employee_id.id == employee_id)
        if department_id:
            lines = lines.filtered(lambda l: l.department_id.id == department_id)
        if not lines:
            return
        if not dates:
            dates = []
            year_month_tuple = set([(line.year, line.month) for line in lines])
            for year_month_tuple in year_month_tuple:
                year = year_month_tuple[0]
                month = year_month_tuple[1]
                year_month_end = datetime(year, month, 1) + relativedelta(day=31)
                dates += [datetime(year, month, day) for day in range(1, year_month_end.day + 1)]
        else:
            dates = [datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) for date in dates]
        year_month_tuples = set([(date.year, date.month) for date in dates])
        dates = [date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT) for date in dates]
        for year_month_tuple in year_month_tuples:
            year = year_month_tuple[0]
            month = year_month_tuple[1]
            payroll_obj = self.env['hr.payroll'].search([
                ('year', '=', year),
                ('month', '=', month)
            ], limit=1)
            if payroll_obj and payroll_obj.busy and not self._context.get('automatic_payroll', False):
                raise exceptions.ValidationError(
                    _('Negalite atlikti šio veiksmo, nes vykdomas atlyginimų skaičiavimas'))
            for line in lines.filtered(lambda l: l.year == year and l.month == month):
                schedule_to_copy_to.with_context(do_not_fill_schedule=True).create_empty_schedule(year, month,
                                                                                          [line.employee_id.id],
                                                                                          [line.department_id.id], True)
                copy_to_line = schedule_to_copy_to.schedule_line_ids.filtered(lambda l:
                                                                              l.employee_id.id == line.employee_id.id and
                                                                              l.department_id.id == line.department_id.id and
                                                                              l.month == month and l.year == year)
                if copy_to_line and copy_to_line.state == 'draft':
                    copy_to_line.mapped('day_ids').filtered(lambda d: d.date in dates).unlink()
                    line_to_copy_to_id = copy_to_line.id
                    current_schedule_days_for_dates = line.day_ids.filtered(lambda d: d.date in dates)
                    for day in current_schedule_days_for_dates:
                        new_day = day.with_context(no_raise=True, bypass_state_change=True).copy(
                            {'work_schedule_line_id': line_to_copy_to_id})
                        day_to_copy_to_id = new_day.id
                        for day_line in day.mapped('line_ids'):
                            day_line.copy({'day_id': day_to_copy_to_id})
                    if not is_planned_schedule:
                        copy_to_line.with_context(bypass_state_change=True).write({'state': line.state})

    @api.model
    def cron_copy_schedule(self):
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        main_work_schedule = self.env.ref('work_schedule.planned_company_schedule')

        month_to_copy_for = datetime.utcnow() + relativedelta(day=31)
        date = month_to_copy_for.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        extended_schedule = self.env.user.company_id.with_context(date=date).extended_schedule
        if not extended_schedule:
            return
        different_dates = [
            str(month_to_copy_for.year) + '-' + str(month_to_copy_for.month).zfill(2) + '-' + str(day).zfill(2) for day
            in range(1, month_to_copy_for.day + 1)]
        main_work_schedule.copy_to_schedule(factual_work_schedule, dates=different_dates)

        # Automatically set planned schedule to be used_as_planned_schedule_in_calculations
        planned_schedule_lines = self.env['work.schedule.line'].search([
            ('month', '=', month_to_copy_for.month),
            ('year', '=', month_to_copy_for.year),
            ('work_schedule_id', '=', main_work_schedule.id)
        ])

        # Set only those lines that have some work time as planned
        lines_to_set_as_planned = self.env['work.schedule.line']
        for line in planned_schedule_lines:
            days = line.mapped('day_ids')
            appointments = days.mapped('appointment_id')
            all_schedules_are_fixed = not any(
                appointment.schedule_template_id.template_type in ('individualus', 'lankstus', 'sumine')
                for appointment in appointments
            )
            if all_schedules_are_fixed:
                continue  # Don't set the line as planned since all of the schedule template types are fixed
            day_lines = days.mapped('line_ids').filtered(lambda l: not l.work_schedule_code_id.is_holiday and
                                                                   not l.work_schedule_code_id.is_absence)
            worked_time = sum(day_lines.mapped('worked_time_total'))
            if not tools.float_is_zero(worked_time, precision_digits=2):
                lines_to_set_as_planned |= line

        lines_to_set_as_planned.write({'used_as_planned_schedule_in_calculations': True})

    @api.model
    def set_default_fill_in_work_schedule_mail_channel_subscribers(self):
        fill_schedule_reminder_mail_channel = self.env.ref('work_schedule.fill_schedule_reminder_mail_channel',
                                                           raise_if_not_found=False)
        if not fill_schedule_reminder_mail_channel:
            return

        work_schedule_manager_group = self.env.ref('work_schedule.group_schedule_manager')
        management_group_users = work_schedule_manager_group.users
        management_group_users = management_group_users.filtered(lambda user: not user.is_accountant() and
                                                                              not user.email.endswith('robolabs.lt'))

        partners_to_subscribe = management_group_users.mapped('partner_id')

        employees_managing_individual_departments = self.env['hr.employee'].search([
            '|',
            ('validate_department_ids', '!=', False),
            ('confirm_department_ids', '!=', False)
        ])

        partners_to_subscribe |= employees_managing_individual_departments.mapped('address_home_id')

        fill_schedule_reminder_mail_channel.write({
            'channel_partner_ids': [(5, 0,)] + [(4, pid) for pid in partners_to_subscribe.ids]
        })

    @api.model
    def cron_reminder_to_fill_in_work_schedule(self):
        """
        Checks for accumulative work time accounting appointments and informs partners that it's time to fill in work
        schedule
        """

        # Only run cron one week before the month ends
        now_dt = datetime.utcnow()
        last_day = now_dt + relativedelta(day=31)
        week_before_month_ends = last_day - relativedelta(days=6)
        week_before_month_ends = week_before_month_ends.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        now = now_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if now != week_before_month_ends:
            return

        extended_schedule = self.env.user.company_id.with_context(date=now).extended_schedule
        if not extended_schedule:
            return

        # Get dates of the following month
        next_month = now_dt + relativedelta(months=1, day=1)
        start_of_next_month = next_month.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        end_of_next_month = (next_month + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Find accumulative work time appointments for next month
        accumulative_work_time_accounting_appointments = self.env['hr.contract.appointment'].search([
            ('schedule_template_id.template_type', '=', 'sumine'),
            ('date_start', '<=', end_of_next_month),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', start_of_next_month)
        ])

        employees = accumulative_work_time_accounting_appointments.mapped('employee_id')

        # Find affected work schedule lines of next month that have not yet been confirmed
        affected_work_schedule_lines = self.env['work.schedule.line'].search([
            ('work_schedule_id', '=', self.env.ref('work_schedule.planned_company_schedule').id),
            ('state', '=', 'draft'),
            ('year', '=', next_month.year),
            ('month', '=', next_month.month),
            ('employee_id', 'in', employees.ids)
        ])

        if not affected_work_schedule_lines:
            return

        # Send reminders
        self.remind_partners_to_fill_in_work_schedule()

    @api.model
    def remind_partners_to_fill_in_work_schedule(self):
        """Posts a message on work schedule fill in reminder mail channel for related partners to fill in schedules"""
        fill_schedule_reminder_mail_channel = self.env.ref('work_schedule.fill_schedule_reminder_mail_channel',
                                                           raise_if_not_found=False)
        if not fill_schedule_reminder_mail_channel:
            return

        subject = _('RoboLabs reminder to fill in work schedules for next month')
        body = _('''Hello,
        <br> 
        We kindly inform you that according to section 2 of article 115 of the labour code of the Republic of Lithuania, 
        it is mandatory to inform employees of their schedule 7 days in advance.
        <br><br>
        Work schedules should be filled in such a way that they are as close to an employee's work norm as possible. The 
        deadline to fill in work schedules for next month is the last day of the current month.
        <br><br>
        If you have already filled in the work schedules for next month - please ignore this email.
        <br><br>
        If you wish to no longer receive such emails - you can unsubscribe from the work schedule fill in mail channel 
        on the RoboLabs platform by clicking "My Profile".
        ''')

        channel_partner_ids = fill_schedule_reminder_mail_channel.sudo().mapped('channel_partner_ids')

        msg = {
            'body': body,
            'subject': subject,
            'message_type': 'comment',
            'subtype': 'mail.mt_comment',
            'priority': 'high',
            'front_message': True,
            'rec_model': 'work.schedule',
            'partner_ids': channel_partner_ids.ids
        }
        fill_schedule_reminder_mail_channel.sudo().robo_message_post(**msg)

    @api.model
    def cron_inform_about_truancy_lines(self):
        now = datetime.now()
        last_midnight = now + relativedelta(hour=0, minute=0, second=0)
        one_day_ago = last_midnight - relativedelta(days=1)
        truancy_lines_created_yesterday = self.env['work.schedule.day.line'].search([
            ('create_date', '>=', one_day_ago.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),
            ('create_date', '<', last_midnight.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),
            ('work_schedule_code_id', '=', self.env.ref('work_schedule.work_schedule_code_PB').id),
            ('state', '!=', 'done')
        ])
        if not truancy_lines_created_yesterday:
            return
        employees = ', '.join(truancy_lines_created_yesterday.mapped('employee_id.address_home_id.name'))
        subject = _('Truancy time has been set in work schedule')
        body = _('Some truancy time has been set in work schedule for the following employees: {}. You '
                 'should review this truancy time, ensure a corresponding act exists and submit the necessary info to '
                 'SoDra.').format(employees)
        try:
            ticket_obj = self.env['mail.thread']._get_ticket_rpc_object()
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': self._name,
                'ticket_record_id': False,
                'name': subject,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'description': body,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError(_('The distant method did not create the ticket.'))
        except Exception as exc:
            message = 'Failed to create work schedule truancy check ticket. Exception: %s' % str(exc.args)
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })

    @api.model
    def determine_work_schedule(self, date):
        next_month_date = (datetime.utcnow() + relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if date >= next_month_date:
            return self.env.ref('work_schedule.planned_company_schedule')
        else:
            return self.env.ref('work_schedule.factual_company_schedule')

    @api.model
    def find_missing_schedule_contracts(self, date, work_schedule=None, departments=None):
        if not work_schedule:
            work_schedule = self.determine_work_schedule(date)  # Determine work schedule

        # Parse date
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        month = date_dt.month
        year = date_dt.year

        # Find employees already in work schedule
        employees_in_schedule = self.env['work.schedule.line'].sudo().search([
            ('month', '=', month),
            ('year', '=', year),
            ('work_schedule_id', '=', work_schedule.id)
        ]).mapped('employee_id')

        # Find ongoing contracts for the period
        next_month_date = (date_dt + relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        first_of_month = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        contract_domain = [
            ('employee_id', 'not in', employees_in_schedule.ids),
            ('date_start', '<', next_month_date),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', first_of_month)
        ]
        if departments:
            contract_domain.append(('employee_id.department_id', 'in', departments.ids))
        contracts = self.env['hr.contract'].sudo().search(contract_domain)
        return contracts

    @api.model
    def create_empty_schedule_for_missing_employees(self, date):
        contracts = self.find_missing_schedule_contracts(date)
        work_schedule = self.determine_work_schedule(date)
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        month = date_dt.month
        year = date_dt.year
        for contract in contracts:
            department_id = contract.department_id.id or contract.employee_id.department_id.id
            try:
                work_schedule.create_empty_schedule(year, month, [contract.employee_id.id], [department_id], False)
            except:
                pass

    @api.model
    def cron_create_empty_schedule_for_missing_employees(self):
        now = datetime.utcnow()
        date = now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        # Don't execute if schedule is disabled or on the first day of the month, because on the first day of the month
        # another cron is performed - cron_work_schedule_copy_to_factual
        if not self.env.user.company_id.with_context(date=date).extended_schedule or now.day == 1:
            return
        month_start = (now + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        month_end = (now + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        has_closed_ziniarastis = self.env['ziniarastis.period'].search_count([
            ('date_from', '=', month_start),
            ('date_to', '=', month_end),
            ('state', '=', 'done'),
        ])
        if has_closed_ziniarastis:
            return

        self.create_empty_schedule_for_missing_employees(date)

    @api.model
    def perform_missing_employee_validation(self, year, month, work_schedule=None, departments=None):
        """ Find missing employees for provided period, schedule and departments and warn about them"""
        first_of_month = datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        missing_contracts = self.find_missing_schedule_contracts(first_of_month, work_schedule, departments)
        if not missing_contracts:
            return ''
        warning = _('Rastos darbuotojų sutartys, tačiau šių darbuotojų grafike nėra:') + '\n'
        for missing_employee in missing_contracts.mapped('employee_id'):
            warning += '{}\n'.format(missing_employee.name or missing_employee.address_home_id.name)
        return warning
