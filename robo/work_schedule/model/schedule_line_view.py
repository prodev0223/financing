# -*- coding: utf-8 -*-
from datetime import *

from dateutil.relativedelta import *

from odoo import models, _, api, exceptions, tools


class WorkScheduleLine(models.Model):
    _inherit = 'work.schedule.line'

    @api.model
    def convert_string_to_department_line_ids(self, line_ids=None):
        unknown_err_msg = _(
            'Nenumatyta sistemos klaida. Prašome susisiekti su sistemos administratoriumi')
        if not line_ids:
            raise exceptions.UserError(unknown_err_msg)
        try:
            ids_converted = list()
            for i in range(0, len(line_ids[0].split(','))):
                ids_converted.append(int(line_ids[0].split(',')[i]))
            return ids_converted
        except:
            raise exceptions.UserError(unknown_err_msg)

    @api.model
    def unlink_all_day_lines(self, day_ids):
        days = self.env['work.schedule.day'].browse(day_ids)
        days.mapped('work_schedule_line_id').ensure_not_busy()
        days.check_state_rules()
        if not self.env.user.is_schedule_super():
            is_manager = self.env.user.is_schedule_manager()
            department_ids = set(days.mapped('department_id.id'))

            cant_modify_own = any(employee_id.id not in self.env.user.employee_ids.ids or not employee_id.sudo().can_fill_own_schedule for employee_id in days.mapped('employee_id'))

            if not is_manager and not self.env.user.can_modify_schedule_departments(department_ids) and cant_modify_own:
                raise exceptions.UserError(_('Negalite ištrinti eilučių, nes negalite keisti visų skyrių eilučių'))
            user_department_ids = self.env.user.mapped('employee_ids.department_id.id') + \
                                  self.env.user.mapped('employee_ids.fill_department_ids.id')
            if any(department_id not in user_department_ids for department_id in department_ids):
                if cant_modify_own:
                    raise exceptions.ValidationError(_('Neturite teisės ištrinti eilučių.'))

        holidays_exist = any(day.holiday_ids and day.holidays_for_the_entire_day for day in days)
        if holidays_exist:
            raise exceptions.UserError(_("You can not delete the selected records since there's an approved leave for "
                                         "the selected days"))

        work_schedule_holidays = days.mapped('schedule_holiday_id')
        holidays_exist = bool(work_schedule_holidays)
        for holiday in work_schedule_holidays:
            holiday.day_ids.filtered(
                lambda d: d.work_schedule_id in days.mapped('work_schedule_id')
            ).check_state_rules()
        work_schedule_holidays.unlink()

        if not holidays_exist:
            days.mapped('line_ids').unlink()

    @api.model
    def remove_schedule_department_line(self, line_ids=None):
        line_ids = self.convert_string_to_department_line_ids(line_ids)
        line_ids = self.browse(line_ids)
        if not line_ids.has_access_rights_to_modify():
            raise exceptions.UserError(_('Negalite keisti šio vartotojo grafiko'))
        if any(state != 'draft' for state in set(line_ids.mapped('state'))):
            raise exceptions.UserError(_('Negalite ištrinti šios eilutės, nes yra įrašų kurie nėra juodraščio būsenos.'))
        line_ids.ensure_not_busy()
        line_ids.unlink()

    @api.model
    def action_set_lines_as_used_in_planned_schedule(self, line_ids=None):
        line_ids = self.convert_string_to_department_line_ids(line_ids)
        line_ids = self.browse(line_ids)
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Tik buhalteriai gali atlikti šią operaciją'))
        if line_ids:
            line_ids.write({'used_as_planned_schedule_in_calculations': not line_ids.mapped('used_as_planned_schedule_in_calculations')[0]})

    @api.model
    def increase_state(self, line_ids=None):
        line_ids = self.browse(self.convert_string_to_department_line_ids(line_ids))
        for state in set(line_ids.mapped('state')):
            state_line_ids = line_ids.filtered(lambda l: l.state == state)
            if state == 'draft':
                state_line_ids.action_validate()
            elif state == 'validated':
                state_line_ids.action_confirm()
            elif state == 'confirmed':
                state_line_ids.action_done()
            else:
                raise exceptions.UserError(_('Negalima įvykdyti tolimesnio grafiko tvirtinimo'))

    @api.model
    def decrease_state(self, line_ids=None):
        line_ids = self.browse(self.convert_string_to_department_line_ids(line_ids))
        for state in set(line_ids.mapped('state')):
            state_line_ids = line_ids.filtered(lambda l: l.state == state)
            if state == 'validated':
                state_line_ids.action_cancel_validate()
            elif state == 'confirmed':
                state_line_ids.action_cancel_confirm()
            elif state == 'done':
                state_line_ids.action_cancel_done()
            else:
                raise exceptions.UserError(_('Negalima įvykdyti tolimesnio grafiko tvirtinimo'))

    @api.model
    def read_schedule(self, year, month, employee_ids=None, department_ids=None, first_fetch=False, extra_domain=None, work_schedule_id=None, offset=0, limit=20):
        if not year or not month:
            raise exceptions.ValidationError(_('Nenurodytas periodas'))
        domain = [('year', '=', year), ('month', '=', month)]

        user = self.env.user
        user_employees = user.employee_ids
        first_of_month = datetime(year, month, 1)
        allow_bypass_constraints = self.sudo().env.user.company_id.work_schedule_labour_code_bypass == 'allowed'
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        today = datetime.utcnow()
        end_of_current_month = today + relativedelta(day=31)
        date_from = first_of_month
        date_to = first_of_month + relativedelta(day=31)
        date_from_str = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_str = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        schedule_user_group = user.get_work_schedule_access_level()

        # Force schedule types for users that are lower group than schedule super or schedule that's for current month
        # or later periods and the user is schedule super but not the accountant.
        if not work_schedule_id or schedule_user_group < 3 or (end_of_current_month < date_to and schedule_user_group == 3):
            work_schedule_id = planned_work_schedule.id if today <= first_of_month else factual_work_schedule.id

        # Force work schedule
        domain.append(('work_schedule_id.id', '=', work_schedule_id))

        # Show only the specified employees
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))

        # Show the schedule for the employee department if it's the first fetch (no department specified)
        if first_fetch and not department_ids:
            default_department = user_employees and user_employees[0].department_id.id or False
            department_ids = [default_department] if default_department else False

        # Filter schedule lines by department
        if department_ids:
            domain.append(('department_id', 'in', department_ids))

        # Add extra domain
        if extra_domain:
            for domain_element in extra_domain:
                if domain_element in ['|', '&']:
                    domain.append(domain_element)
                else:
                    domain.append(tuple(domain_element))

        month_has_been_validated = self.sudo().env['ziniarastis.period'].search_count([
            ('date_from', '=', date_from_str),
            ('date_to', '=', date_to_str),
            ('state', '=', 'done')
        ]) > 0

        national_holiday_dates = self.env['sistema.iseigines'].search([
            ('date', '<=', date_to_str),
            ('date', '>=', date_from_str)
        ]).mapped('date')

        weekend_dates = list()
        day_print_data = {}

        weekday_day_map = [_('Pirm.'), _('Antr.'), _('Treč.'), _('Ketv.'), _('Penk.'), _('Šešt.'), _('Sekm.')]

        while date_from <= date_to:
            date_str = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            is_weekend = False
            if date_from.weekday() in [5, 6]:
                is_weekend = True
                weekend_dates.append(date_str)
            day_print_data[date_str] = {
                'is_weekend': is_weekend,
                'is_national_holiday': date_str in national_holiday_dates,
                'is_today': date_from == today,
                'print_str': str(date_from.day) + ', ' + weekday_day_map[date_from.weekday()],
            }
            date_from += relativedelta(days=1)

        lines = self.search(domain)
        total_number_of_lines = len(lines)
        lines = lines.sorted(lambda l: l.employee_id.name)[offset:offset+limit]
        single_department_filtered = len(set(lines.mapped('department_id.id'))) == 1
        data = lines.parse_lines_to_dict()
        department_line_totals = lines.get_line_totals()
        dates_totals = lines.get_day_totals(year, month)

        line_departments = lines.mapped('department_id.id')
        if user.can_modify_schedule_departments(line_departments, False) or \
            user.can_validate_schedule_departments(line_departments, False):
            schedule_user_group = max(schedule_user_group, 2)
        if user.can_confirm_schedule_departments(line_departments, False):
            schedule_user_group = max(schedule_user_group, 3)

        user_department_ids = user_employees.mapped('department_id.id') + \
                              user_employees.mapped('fill_department_ids.id') + \
                              user_employees.mapped('confirm_department_ids.id') + \
                              user_employees.mapped('validate_department_ids.id')

        month_name_map = {
            1: _('Sausis'),
            2: _('Vasaris'),
            3: _('Kovas'),
            4: _('Balandis'),
            5: _('Gegužė'),
            6: _('Birželis'),
            7: _('Liepa'),
            8: _('Rugpjūtis'),
            9: _('Rugsėjis'),
            10: _('Spalis'),
            11: _('Lapkritis'),
            12: _('Gruodis'),
        }

        work_schedule = self.env['work.schedule'].browse(work_schedule_id)
        curr_month_start = today + relativedelta(day=1)
        self_month_start = datetime(year, month, 1)
        work_schedule_is_planned = work_schedule == planned_work_schedule
        payroll = self.env['hr.payroll'].sudo().search([('year', '=', year), ('month', '=', month)])
        payroll_busy = bool(payroll) and payroll.busy
        force_show_edit_buttons = not any(line.employee_id.id not in user_employees.ids or not line.employee_id.sudo().can_fill_own_schedule for line in lines)
        if not lines:
            force_show_edit_buttons = False

        # Prevent editing the schedule if the user is not an accountant and is viewing the planned schedule.
        if work_schedule_is_planned and schedule_user_group < 4 and self_month_start <= curr_month_start:
            force_show_edit_buttons = False

        button_statuses = lines.get_button_statuses()

        disable_state_changes = self_month_start <= curr_month_start and work_schedule_is_planned
        if disable_state_changes:
            keys_to_keep = ['allow_go_to_date']
            for status_key in button_statuses.keys():
                if status_key in keys_to_keep:
                    continue
                button_statuses[status_key] = False

        res = {
            'month_validated': month_has_been_validated,
            'day_print_data': day_print_data,
            'weekends': weekend_dates,
            'national_holidays': national_holiday_dates,
            'department_line_totals': department_line_totals,
            'dates_totals': dates_totals,
            'single_department_filtered': single_department_filtered,
            'single_department_name': lines.mapped('department_id.name')[0] if lines else False,
            'schedule': data,
            'month_name': month_name_map[month],
            'num_month_days': (datetime(year, month, 1)+relativedelta(day=31)).day,
            'dynamic_buttons': button_statuses,
            'user_group': schedule_user_group,
            'force_show_edit_buttons': force_show_edit_buttons,
            'user_department_ids': user_department_ids,
            'work_schedule_id': work_schedule_id,
            'work_schedule_is_planned': work_schedule_is_planned,
            'disable_state_changes': disable_state_changes,
            'allow_bypass_constraints': allow_bypass_constraints,
            'hide_busy_label': not payroll_busy or schedule_user_group < 4,
            'total_number_of_lines': total_number_of_lines,
        }
        return res

    @api.multi
    def get_line_totals(self):
        line_values = {}
        factual_schedule = self.env.ref('work_schedule.factual_company_schedule').id
        employee_ids = self.env.user.mapped('employee_ids')
        if not self:
            return {}
        if not self.env.user.is_schedule_manager():
            user_departments = employee_ids.mapped('department_id.id') + employee_ids.mapped('fill_department_ids.id') + \
                               employee_ids.mapped('validate_department_ids.id') + employee_ids.mapped('confirm_department_ids.id')
            self = self.filtered(lambda l: l.department_id.id in user_departments or l.employee_id.id in employee_ids.ids)
            if not self:
                raise exceptions.UserError(_('Neturite teisės matyti eilučių dirbto laiko sumų'))
        user = self.env.user
        self = self.sudo()
        forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', self.mapped('employee_id').ids),
            ('date', 'in', self.mapped('day_ids.date')),
        ])
        for line in self:
            days_to_calculate_for = line.mapped('day_ids')
            if line.work_schedule_id.id == factual_schedule or \
                    datetime(line.year, line.month, 1) > datetime.utcnow() and not user.is_accountant():
                days_to_calculate_for = days_to_calculate_for.filtered(lambda d: not d.schedule_holiday_id or (
                    any(
                        d.date == forced_work_time_day.date and
                        d.employee_id == forced_work_time_day.employee_id
                        for forced_work_time_day in forced_work_times
                    ))
                )
            date_lines_to_calculate_for = days_to_calculate_for.mapped('line_ids').filtered(lambda l: not tools.float_is_zero(l.worked_time_total, precision_digits=2))
            hours_sum = sum(date_lines_to_calculate_for.mapped('worked_time_total'))
            days_sum = len(set(date_lines_to_calculate_for.mapped('day_id')))
            line_values[line.id] = {
                'hours': hours_sum,
                'days': days_sum,
            }
        return line_values

    @api.multi
    def get_day_totals(self, year, month):
        days = self.mapped('day_ids')
        date_to = datetime(year, month, 1)+relativedelta(day=31)
        dates = [str(year) + '-' + str(month).zfill(2) + '-' + str(day).zfill(2) for day in range(1, date_to.day + 1)]
        return_dates = {}
        employee_ids = self.env.user.mapped('employee_ids')
        if not self.env.user.is_schedule_manager():
            user_departments = employee_ids.mapped('department_id.id') + employee_ids.mapped('fill_department_ids.id') + \
                               employee_ids.mapped('validate_department_ids.id') + employee_ids.mapped('confirm_department_ids.id')
            if any(department not in user_departments for department in days.mapped('department_id.id')):
                self = self.filtered(lambda l: l.employee_id.id in employee_ids.ids or l.employee_id.id in employee_ids.ids)
                if not self:
                    raise exceptions.UserError(_('Neturite teisės matyti eilučių dirbto laiko sumų'))
        days = days.sudo()
        forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', days.mapped('employee_id').ids),
            ('date', 'in', dates),
        ])
        factual_schedule = self.env.ref('work_schedule.factual_company_schedule').id in days.mapped('work_schedule_id.id')
        if factual_schedule or datetime(year, month, 1) > datetime.utcnow() and not self.env.user.is_accountant():
            days = days.filtered(lambda d: not d.schedule_holiday_id or (
                any(
                    d.date == forced_work_time_day.date and
                    d.employee_id == forced_work_time_day.employee_id
                    for forced_work_time_day in forced_work_times
                )
            ))
        for date in dates:
            date_day_line_ids = days.filtered(lambda d: d.date == date).mapped('line_ids').filtered(lambda l: not tools.float_is_zero(l.worked_time_total, precision_digits=2))
            hours_sum = sum(date_day_line_ids.mapped('worked_time_total'))
            days_sum = len(set(date_day_line_ids.mapped('day_id')))
            return_dates[date] = {
                'hours': hours_sum,
                'days': days_sum,
            }
        return return_dates

    @api.multi
    def parse_lines_to_dict(self):
        '''
        Creates a dict of values with all days lines and holidays for JS
        this looks complicated af but really is not and should be better than previous payroll schedule
        :return: dict of department line values with days lines and holidays
        '''
        # start = time.time()
        data = {}
        if not self:
            return data
        if len(set(self.mapped('year'))) > 1 or len(set(self.mapped('month'))) > 1:
            raise exceptions.UserError(_('Duomenų apdorojimas leidžiamas tik vienam periodui vienu metu'))

        period_month = self.mapped('month')[0]
        period_year = self.mapped('year')[0]
        period_start_dt = datetime(period_year, period_month, 1)
        period_end_dt = (period_start_dt + relativedelta(day=31))
        period_end = period_end_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        period_start = period_start_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Do not show user holidays if main schedule is being viewed
        main_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        fetch_user_holidays = True
        if main_work_schedule.id in self.mapped('work_schedule_id.id') and (period_start_dt <= datetime.utcnow() or self.env.user.is_accountant()):
            fetch_user_holidays = False

        employee_ids = self.mapped('employee_id.id')
        work_schedule_line_ids = self.mapped('id')

        forced_work_times = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', employee_ids),
            ('date', '>=', period_start),
            ('date', '<=', period_end)
        ])

        self._cr.execute('''
                    SELECT
                        employee.id AS id,
                        employee.name_related AS name,
                        CASE WHEN employee.job_id is NULL THEN Null ELSE hr_job.name END AS job_name
                    FROM
                        hr_employee employee
                    LEFT OUTER JOIN
                        hr_job ON (employee.job_id = hr_job.id)
                    WHERE
                        employee.id IN %s
        	    ''', (tuple(employee_ids),))
        all_employee_data = self._cr.dictfetchall()

        self._cr.execute('''
                            SELECT
                                employee_id,
                                date_start,
                                date_end
                            FROM
                                hr_contract contract
                            WHERE
                                contract.employee_id IN %s
                	    ''', (tuple(employee_ids),))
        all_contract_data = self._cr.dictfetchall()

        self._cr.execute('''
            SELECT
                line.id AS id,
                line.department_id AS department_id,
                department.name AS department_name,
                line.state AS state,
                line.employee_id AS employee_id,
                line.used_as_planned_schedule_in_calculations AS used_in_planned,
                employee.name_related AS employee_name,
                line.constraint_check_data AS constraint_check_data,
                line.busy AS busy
            FROM
                work_schedule_line line
            INNER JOIN
                hr_department department ON (department.id = line.department_id)
            INNER JOIN
                hr_employee employee ON (employee.id = line.employee_id)
            WHERE
                line.id IN %s
        ''', (tuple(work_schedule_line_ids),))
        work_schedule_line_data = self._cr.dictfetchall()
        if fetch_user_holidays:
            self._cr.execute('''
                SELECT
                    holiday.id AS id,
                    holiday.employee_id AS employee_id,
                    holiday.date_from AS date_from,
                    holiday.date_to AS date_to,
                    holiday_status.kodas AS tabelio_zymejimas_code,
                    CASE WHEN EXISTS (
                        SELECT id
                        FROM 
                            hr_holidays
                        WHERE
                            state = 'validate' AND
                            employee_id = employee_id AND
                            date_from_date_format < date_to AND
                            date_to_date_format > date_from AND
                            holiday_status_id = holiday.holiday_status_id
                    ) THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS is_confirmed 
                FROM
                    work_schedule_holidays holiday
                INNER JOIN
                    hr_holidays_status holiday_status ON (holiday.holiday_status_id = holiday_status.id)
                WHERE 
                    holiday.employee_id IN %s AND
                    holiday.date_from <= %s AND
                    holiday.date_to >= %s AND
                    holiday_status.kodas != 'K'
            ''', (tuple(employee_ids), period_end, period_start))
            work_schedule_holiday_data = self._cr.dictfetchall()
        else:
            work_schedule_holiday_data = {}

        self._cr.execute('''
            SELECT
                day.id AS id,
                day.date AS date,
                day.work_schedule_line_id as line_id,
                day.free_day,
                day.business_trip
            FROM
                work_schedule_day day
            WHERE
                day.work_schedule_line_id IN %s
        ''', (tuple(work_schedule_line_ids),))
        work_schedule_day_data = self._cr.dictfetchall()

        day_ids = [rec['id'] for rec in work_schedule_day_data]

        self._cr.execute('''
            SELECT
                line.name AS name,
                line.day_id AS day_id,
                line.worked_time_total AS worked_time_total,
                line.time_from AS time_from
            FROM
                work_schedule_day_line line
            WHERE
                day_id IN %s
        ''', (tuple(day_ids), ))
        work_schedule_day_line_data = self._cr.dictfetchall()

        month_appointments = self.sudo().env['hr.contract.appointment'].search([
            ('employee_id', 'in', employee_ids),
            ('date_start', '<=', period_end),
            '|',
            ('date_end', '>=', period_start),
            ('date_end', '=', False)
        ])
        empty_line_value = {
            'name': '',
        }
        # Get all dates for month, used for later to make sure JS never fails at rendering also filter iseigines
        month_dates = [
            str(period_year) + '-' + str(period_month).zfill(2) + '-' + str(day).zfill(2) for day in range(1, period_end_dt.day+1)
        ]

        forced_work_time = self.env['hr.employee.forced.work.time'].sudo().search([
            ('employee_id', 'in', employee_ids),
            ('date', '<=', period_end),
            ('date', '>=', period_start)
        ])

        # Group by employee
        for employee_id in employee_ids:
            employee_data = [rec for rec in all_employee_data if rec['id'] == employee_id][0]
            employee_work_schedule_lines = [rec for rec in work_schedule_line_data if rec['employee_id'] == employee_id]
            employee_contract_data = [rec for rec in all_contract_data if rec['employee_id'] == employee_id]
            empl_used_in_planned = any([rec['used_in_planned'] for rec in employee_work_schedule_lines])
            employee_appointments = month_appointments.sudo().filtered(lambda a: a.employee_id.id == employee_id)
            appointment = employee_appointments.sorted(key='date_start', reverse=True)[0] if employee_appointments else False
            etatas = appointment.schedule_template_id.etatas if appointment else False
            employee_forced_work_time_dates = forced_work_time.filtered(
                lambda t: t.employee_id.id == employee_id
            ).mapped('date')
            department_data = {}
            index = 0

            forced_work_dates = forced_work_times.filtered(lambda d: d.employee_id.id == employee_id).mapped('date')

            # Group by department
            for line in sorted(employee_work_schedule_lines, key=lambda k: k['department_name']):
                index += 1
                line_id = line['id']
                constraint_status = self.env['work.schedule.line'].get_constraint_status(
                    line['busy'], line['constraint_check_data']
                )
                department_data[line_id] = {
                    'name': line['department_name'],
                    'state': line['state'],
                    'department_id': line['department_id'],
                    'constraint_status': constraint_status
                }
                department_days = [rec for rec in work_schedule_day_data if rec['line_id'] == line_id]
                # Group by date
                for date in month_dates:
                    line_vals = list()
                    date_day = [rec for rec in department_days if rec['date'] == date]
                    work_schedule_day_ids = [date_rec['id'] for date_rec in date_day]
                    date_work_schedule_days = self.env['work.schedule.day'].sudo().browse(work_schedule_day_ids)
                    date_day_holidays = False
                    if fetch_user_holidays:
                        date_day_holidays = [{
                            'id': holiday.id,
                            'is_confirmed': 1,
                            'employee_id': holiday.employee_id.id,
                            'date_from': holiday.date_from_date_format,
                            'date_to': holiday.date_to_date_format,
                            'tabelio_zymejimas_code': holiday.holiday_status_id.kodas,
                        } for holiday in date_work_schedule_days.filtered(lambda d: d.holidays_for_the_entire_day).mapped('holiday_ids')]
                        if not date_day_holidays:
                            date_day_holidays = [
                                rec for rec in work_schedule_holiday_data if
                                rec['date_from'] <= date <= rec['date_to'] and
                                rec['employee_id'] == line['employee_id']
                            ]
                    has_contract = any(rec['date_start'] <= date and (not rec['date_end'] or rec['date_end'] >= date) for rec in employee_contract_data)
                    user_holiday = bool(date_day_holidays) and date not in forced_work_dates
                    if user_holiday:
                        date_day_holidays = date_day_holidays[0]
                        user_holiday = {
                            'id': date_day_holidays['id'],
                            'code': date_day_holidays['tabelio_zymejimas_code'],
                            'date_from': date_day_holidays['date_from'],
                            'date_to': date_day_holidays['date_to'],
                            'is_confirmed': date_day_holidays['is_confirmed']
                        }
                    total_value = 0.0

                    if date_day:
                        date_day = date_day[0]

                    date_day_lines = [rec for rec in work_schedule_day_line_data if rec['day_id'] == date_day['id']] if date_day else False

                    if not date_day or (not date_day_lines and not date_day['business_trip'] and not date_day['free_day']):
                        line_vals.append(empty_line_value)
                    else:
                        for day_line in sorted(date_day_lines, key=lambda k: k['time_from']):
                            total_value += day_line['worked_time_total'] if day_line['worked_time_total'] else 0.0
                            if day_line['name']:
                                line_vals.append({
                                    'name': day_line['name'],
                                })
                        if date_day['free_day']:
                            line_vals.append({
                                'name': 'P',
                            })
                        elif date_day['business_trip']:
                            line_vals.append({
                                'name': 'K',
                            })

                    date_vals = {
                        'is_hidden': user_holiday and index != 1,  # Used for cell merging for holidays
                        'user_holiday': user_holiday if date not in employee_forced_work_time_dates else False,
                        'value': total_value,
                        'id': date_day['id'],
                        'lines': line_vals,
                        'has_contract': has_contract,
                    }
                    department_data[line_id][date] = date_vals

            data[employee_id] = {
                'name': employee_data['name'],
                'job': employee_data['job_name'] or '',
                'etatas': round(etatas, 5),
                'department_data': department_data,
                'empl_used_in_planned': empl_used_in_planned,
            }
        return data


WorkScheduleLine()
