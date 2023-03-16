# -*- coding: utf-8 -*-
import ast
from datetime import datetime
from math import floor

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools, exceptions
from odoo.tools.translate import _

from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES

def format_totals_to_hours(totals):
    pattern = '%02d:%02d'
    if totals < 0:
        totals = abs(totals)
        pattern = '-' + pattern
    hour = floor(totals)
    min = round((totals % 1) * 60)
    if min == 60:
        min = 0
        hour = hour + 1
    return pattern % (hour, min)

class MainScheduleSetter(models.TransientModel):
    _name = 'main.schedule.setter'
    _inherit = 'base.schedule.setter'

    work_hours_from = fields.Float(string='Laikas nuo')
    work_hours_to = fields.Float(string='Laikas iki')
    break_hours_from = fields.Float(string='Pertraukos laikas nuo')
    break_hours_to = fields.Float(string='Pertraukos laikas iki')
    lunch_break = fields.Boolean(string='Pertrauka', default=True)
    free_day = fields.Boolean(string='Poilsio diena')
    business_trip = fields.Boolean(string='Komandiruotė')
    len_day_ids_selected = fields.Integer(string='Grafiko keičiamų dienų skaičius', compute='_compute_len_day_ids_selected')
    date = fields.Char(string="Data", compute='_compute_dates')
    first_day_of_month = fields.Boolean(compute='_compute_dates')
    last_day_of_month = fields.Boolean(compute='_compute_dates')
    sum_before_changes = fields.Char(string='Prieš pakeitimus', compute='_compute_times')
    sum_after_changes = fields.Char(string='Po pakeitimų', compute='_compute_times')
    expected_work_hours = fields.Char(string='Darbo norma', compute='_compute_times')
    setter_type = fields.Selection([('simple', _('Paprastas')), ('extended', _('Išplėstinis'))], string='Pildymo būdas', default='simple')
    line_ids = fields.One2many('main.setter.worked.time.line', 'main_schedule_setter_id', string='Darbo laikas')
    sumine_text = fields.Char(compute='_compute_sumine_text')
    show_break_text = fields.Boolean(compute='_compute_show_break_text')

    @api.one
    @api.depends('free_day', 'lunch_break', 'work_hours_from', 'work_hours_to', 'setter_type', 'line_ids.time_from', 'line_ids.time_to')
    def _compute_show_break_text(self):
        self.show_break_text = False
        if not self.free_day:
            if self.setter_type == 'simple':
                worked_time = self.work_hours_to - self.work_hours_from
                if not self.lunch_break and tools.float_compare(worked_time, 5.0, precision_digits=2) > 0:
                    self.show_break_text = True
            else:
                fd_code = self.env.ref('work_schedule.work_schedule_code_FD')
                fd_lines = self.line_ids.filtered(lambda l: l.work_schedule_code_id.id == fd_code.id)
                if len(fd_lines) >= 1 and tools.float_compare(sum(fd_lines.mapped('time_total')), 5.0, precision_digits=2) > 0:
                    if len(fd_lines) == 1:
                        self.show_break_text = True
                    else:
                        end_times = fd_lines.mapped('time_to')
                        start_times = fd_lines.mapped('time_from')
                        end_times.sort()
                        start_times.sort()
                        line_len = len(fd_lines)
                        do_show = True
                        for i in range(0, line_len):
                            if i != line_len-1:
                                curr_end_time = end_times[i]
                                next_start_time = start_times[i+1]
                                diff = next_start_time - curr_end_time
                                atleast_half_an_hour = tools.float_compare(diff, 0.5, precision_digits=2) >= 0
                                if atleast_half_an_hour:
                                    do_show = False
                                    break
                        self.show_break_text = do_show

    @api.one
    @api.depends('day_schedule_ids')
    def _compute_sumine_text(self):
        self.sumine_text = ''

        if not self.env.user.is_schedule_manager() and not self.env.user.can_modify_schedule_departments(self.day_schedule_ids.mapped('department_id.id')):
            return

        worked_time_codes = PAYROLL_CODES['WORKED'] + PAYROLL_CODES['OUT_OF_OFFICE'] + \
                            PAYROLL_CODES['UNPAID_OUT_OF_OFFICE'] + PAYROLL_CODES['DOWNTIME']

        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')

        def _dt(date):
            return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        def find_sumine_period(date):
            calc_from = period_start_dt
            date_dt = _dt(date)
            months_between = relativedelta(date_dt, calc_from).months
            months_before = months_between % period_amount
            calc_from_dt = date_dt - relativedelta(months=months_before, day=1)
            calc_to_dt = calc_from_dt + relativedelta(months=period_amount-1, day=31)
            return (_strf(calc_from_dt), _strf(calc_to_dt))

        def get_dates(date_from, date_to):
            """
            Creates a list of dates between two dates
            Args:
                date_from (date): date from
                date_to (date): date to
            Returns: list of dates between given dates
            """
            dates_list = list()
            date_from_dt, date_to_dt = _dt(date_from), _dt(date_to)
            while date_from_dt <= date_to_dt:
                dates_list.append(_strf(date_from_dt))
                date_from_dt += relativedelta(days=1)
            return dates_list

        def get_periods(period_dates):
            """
            Gets the periods (date_from, date_to) from a list of dates
            Args:
                period_dates (list): list of dates to get the periods for
            Returns: list of periods for given dates

            >>> get_periods(['2021-01-01', '2021-01-02', '2021-01-03', '2021-01-05', '2021-01-06'])
            [['2021-01-01', '2021-01-03'], ['2021-01-05', '2021-01-06']]
            """
            periods = list()
            period_dates.sort()
            date_period = None
            for date in period_dates:
                if not date_period:
                    date_period = [date, False]
                date_dt = _dt(date)
                next_day = _strf(date_dt + relativedelta(days=1))
                if next_day not in period_dates:
                    date_period[1] = date
                    periods.append(date_period)
                    date_period = None
            return periods

        day_ids = self.day_schedule_ids
        if not day_ids:
            return
        dates = day_ids.mapped('date')

        employees = day_ids.mapped('employee_id')
        if len(employees) != 1:
            return
        employee = employees

        min_date, max_date = min(dates), max(dates)

        company = self.env.user.company_id
        accumulative_accounting_start = company.sumine_apskaita_period_start
        if accumulative_accounting_start > max_date:
            return

        period_start_dt = _dt(accumulative_accounting_start)
        period_amount = company.sumine_apskaita_period_amount

        text = ''
        accumulative_accounting_periods = set(find_sumine_period(day.date) for day in day_ids)
        for period in accumulative_accounting_periods:
            start, end = period[0], period[1]

            appointments = self.env['hr.contract.appointment'].sudo().search([
                ('employee_id', '=', employee.id),
                ('schedule_template_id.template_type', '=', 'sumine'),
                ('date_start', '<=', end),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', start)
            ])

            if not appointments:
                continue

            accumulative_accounting_dates = list()
            for appointment in appointments:
                date_from, date_to = appointment.date_start, appointment.date_end
                if not date_to:
                    date_to = end
                date_from = max(start, date_from)
                date_to = min(end, date_to)
                accumulative_accounting_dates += get_dates(date_from, date_to)

            period_slips = self.sudo().env['hr.payslip'].search([
                ('state', '=', 'done'),
                ('date_from', '<=', end),
                ('date_to', '>=', start),
                ('employee_id', '=', employee.id),
                ('contract_id.date_start', '<=', end),
                '|',
                ('contract_id.date_end', '=', False),
                ('contract_id.date_end', '>=', start)
            ])

            all_data = {}
            for slip in period_slips:
                slip_start, slip_end = slip.date_from, slip.date_to
                slip_data = slip.get_payslip_sumine_appointment_data()
                all_data.update({
                    'worked_time': all_data.get('worked_time', 0.0) + slip_data.get('worked_time', 0.0),
                    'ndl_hours_to_account_for': all_data.get('ndl_hours_to_account_for', 0.0) + slip_data.get('ndl_hours_to_account_for', 0.0),
                    'ndl_hours_accounted_for': all_data.get('ndl_hours_accounted_for', 0.0) + slip_data.get('ndl_hours_accounted_for', 0.0),
                    'work_norm': all_data.get('work_norm', 0.0) + slip_data.get('work_norm', 0.0),
                    'vdl_hours_to_account_for': all_data.get('vdl_hours_to_account_for', 0.0) + slip_data.get('vdl_hours_to_account_for', 0.0),
                    'vdl_hours_accounted_for': all_data.get('vdl_hours_accounted_for', 0.0) + slip_data.get('vdl_hours_accounted_for', 0.0),
                })
                slip_dates = get_dates(slip_start, slip_end)
                # Remove slip dates from accumulative accounting dates since those periods are accounted for
                accumulative_accounting_dates = [x for x in accumulative_accounting_dates if x not in slip_dates]

            unaccounted_periods = get_periods(accumulative_accounting_dates)

            total_unaccounted_work_norm = total_unaccounted_registered_time = 0.0
            for unaccounted_period in unaccounted_periods:
                u_start = unaccounted_period[0]
                u_end = unaccounted_period[1]
                u_period_app_ids = appointments.filtered(lambda a: a.date_start <= u_end and
                                                                   (not a.date_end or a.date_end >= u_start))
                for u_period_app in u_period_app_ids:
                    total_unaccounted_work_norm += self.sudo().env['hr.employee'].with_context(
                        use_holiday_records=True
                    ).employee_work_norm(
                        calc_date_from=max(u_start, u_period_app.date_start),
                        calc_date_to=min(u_end, u_period_app.date_end or u_end),
                        appointment=u_period_app,
                        skip_leaves=True
                    )['hours']

                work_schedule_days = self.env['work.schedule.day'].search([
                    ('work_schedule_line_id.employee_id', '=', employee.id),
                    ('date', '<=', u_end),
                    ('date', '>=', u_start)
                ]).filtered(lambda d: not d.schedule_holiday_id)

                good_days = self.env['work.schedule.day']

                break_point = _strf(datetime.utcnow() + relativedelta(day=31))
                good_days |= work_schedule_days.filtered(lambda d: d.date <= break_point and
                                                                   d.work_schedule_id.id == factual_work_schedule.id)
                good_days |= work_schedule_days.filtered(lambda d: d.date > break_point and
                                                                   d.work_schedule_id.id == planned_work_schedule.id)
                lines = good_days.mapped('line_ids').exists().sudo().filtered(lambda l: l.code in worked_time_codes)
                total_unaccounted_registered_time += sum(lines.mapped('worked_time_total'))

            diff = total_unaccounted_registered_time - total_unaccounted_work_norm
            # If diff > 0 - VDL, if diff < 0 - NDL, else - All good

            diff += (all_data.get('ndl_hours_accounted_for', 0.0) - all_data.get('ndl_hours_to_account_for', 0.0))
            diff += (all_data.get('vdl_hours_accounted_for', 0.0) - all_data.get('vdl_hours_to_account_for', 0.0)) * -1

            if not tools.float_is_zero(diff, precision_digits=2):
                text_string = '''Periode %s - %s šiam darbuotojui priskaičiuota %s val. %s min '''
                text_string += 'neišdirbta darbo laiko norma\n' if tools.float_compare(diff, 0.0, precision_digits=2) < 0 else 'viršyta darbo laiko norma\n'
                time_hours, time_minutes = divmod(abs(diff) * 60, 60)
                time_minutes = round(time_minutes)
                if tools.float_compare(int(time_minutes), 60, precision_digits=3) == 0:
                    time_minutes = 0
                    time_hours += 1
                text += text_string % (
                    str(period[0]),
                    str(period[1]),
                    str(int(time_hours)),
                    str(int(time_minutes)),
                )
        self.sumine_text = text

    @api.one
    @api.depends('day_schedule_ids')
    def _compute_dates(self):
        self.date = self.first_day_of_month = self.last_day_of_month = False
        if self.len_day_ids_selected == 1:
            self.date = self.day_schedule_ids.date
            date_dt = datetime.strptime(self.day_schedule_ids.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.first_day_of_month = self.date == (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.last_day_of_month = self.date == (date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.one
    @api.depends('day_schedule_ids')
    def _compute_len_day_ids_selected(self):
        self.len_day_ids_selected = len(self.day_schedule_ids)

    @api.one
    @api.depends('work_hours_from', 'work_hours_to', 'break_hours_from', 'break_hours_to', 'lunch_break', 'free_day', 'day_schedule_ids', 'setter_type', 'line_ids')
    def _compute_times(self):
        totals = sum(self.day_schedule_ids.mapped('line_ids.worked_time_total'))
        self.sum_before_changes = format_totals_to_hours(totals)

        calc_date_from = min(self.day_schedule_ids.mapped('date'))
        calc_date_to = max(self.day_schedule_ids.mapped('date'))
        hours = 0.0
        for employee in self.day_schedule_ids.mapped('employee_id'):
            empl_contracts = self.sudo().env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', calc_date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', calc_date_from)
            ])
            for contract in empl_contracts:
                work_norm = self.sudo().env['hr.employee'].employee_work_norm(
                    calc_date_from=calc_date_from,
                    calc_date_to=calc_date_to,
                    contract=contract)
                hours += work_norm['hours']
        self.expected_work_hours = format_totals_to_hours(hours)

        if self.setter_type == 'simple':
            if not self.free_day:
                total = self.work_hours_to - self.work_hours_from
                if self.lunch_break:
                    total -= self.break_hours_to - self.break_hours_from
            else:
                total = 0
        else:
            if not self.free_day:
                total = sum(l.time_to - l.time_from for l in self.line_ids)
            else:
                total = 0
        self.sum_after_changes = format_totals_to_hours(total * self.len_day_ids_selected)

    def open_another_day_setter(self):
        direction = self._context.get('direction', 'next')
        active_ids = self._context.get('active_ids', False)
        if not active_ids and self.day_schedule_ids:
            day = self.day_schedule_ids
        else:
            day = self.env['work.schedule.day'].browse(active_ids)

        last_day_of_month = True if len(day) == 1 and datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT) == (
                datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)) else False
        first_day_of_month = True if len(day) == 1 and datetime.strptime(day.date,
                                                                         tools.DEFAULT_SERVER_DATE_FORMAT) == (
                                             datetime.strptime(day.date,
                                                               tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                                         day=1)) else False
        if len(day) == 1 and ((direction == 'next' and not last_day_of_month) or (direction == 'previous' and not first_day_of_month)):
            date = datetime.strptime(day.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if direction == 'next':
                date += relativedelta(days=1)
            else:
                date -= relativedelta(days=1)

            date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            new_day = self.env['work.schedule.day'].search([('date', '=', date),
                                                          ('employee_id', '=', day.employee_id.id),
                                                          ('department_id', '=', day.department_id.id),
                                                          ('work_schedule_id', '=', day.work_schedule_id.id)], limit=1).id
            action = self.env.ref('work_schedule.action_open_main_schedule_setter').read()[0]
            context = ast.literal_eval(action['context'])
            context.update({'active_ids': [new_day]})
            self.confirm()
            return {
                'type': 'ir.actions.act_window',
                'view_id': [self.env.ref('work_schedule.main_work_schedule_setter_form').id],
                'res_model': 'main.schedule.setter',
                'target': 'new',
                'views': [[[self.env.ref('work_schedule.main_work_schedule_setter_form').id], 'form']],
                'view_type': 'form',
                'view_mode': 'form',
                'context': context,
            }
        else:
            return

    def check_work_hour_constraints(self):
        if tools.float_compare(self.work_hours_from, self.work_hours_to, precision_digits=3) > 0:
            raise exceptions.UserError(_('Darbo pradžia turi būti prieš darbo pabaigą'))
        if self.lunch_break and not self.free_day:
            # if tools.float_compare(self.work_hours_from, self.break_hours_from, precision_digits=3) >= 0:
                # raise exceptions.UserError(_('Pertrauka turi prasidėti po darbo pradžios'))
            if tools.float_compare(self.break_hours_to, self.work_hours_to, precision_digits=3) >= 0:
                raise exceptions.UserError(_('Pertrauka turi pasibaigti prieš darbo pabaigą'))
            if tools.float_compare(self.break_hours_from, self.break_hours_to, precision_digits=3) >= 0:
                raise exceptions.UserError(_('Pertrauka turi prasidėti prieš pertraukos pabaigą'))

    @api.model
    def default_get(self, fields_list):
        res = super(MainScheduleSetter, self).default_get(fields_list)
        work_hours_from = 8.0
        work_hours_to = 17.0
        break_hours_from = 12.0
        break_hours_to = 13.0
        lunch_break = True
        day_ids = self.env['work.schedule.day'].browse(self._context.get('active_ids', []))
        if day_ids:
            sample_day = day_ids[0]
            business_trip = sample_day.business_trip
            lines = sample_day.line_ids.filtered(lambda r: r.code == 'FD')
            if len(lines) == 1:
                work_hours_from = lines.time_from
                work_hours_to = lines.time_to
                break_hours_from = 0.0
                break_hours_to = 0.0
                lunch_break = False
            elif len(lines) == 2:
                lines = lines.sorted(lambda r: r.time_from)
                min_line = lines[0]
                max_line = lines[1]
                work_hours_from = min_line.time_from
                work_hours_to = max_line.time_to
                break_hours_from = min_line.time_to
                break_hours_to = max_line.time_from
                lunch_break = True
        if 'work_hours_from' in fields_list:
            res['work_hours_from'] = work_hours_from
        if 'work_hours_to' in fields_list:
            res['work_hours_to'] = work_hours_to
        if 'break_hours_from' in fields_list:
            res['break_hours_from'] = break_hours_from
        if 'break_hours_to' in fields_list:
            res['break_hours_to'] = break_hours_to
        if 'lunch_break' in fields_list:
            res['lunch_break'] = lunch_break
        if 'business_trip' in fields_list:
            res['business_trip'] = business_trip

        if day_ids and len(day_ids) == 1:
            line_commands = []
            for line in day_ids.mapped('line_ids'):
                vals = {
                    'time_from': line.time_from,
                    'time_to': line.time_to,
                    'work_schedule_code_id': line.work_schedule_code_id.id
                }
                line_commands.append((0, 0, vals))
            res['line_ids'] = line_commands
        return res

    @api.multi
    def confirm(self):
        self.ensure_one()
        self.check_rights_to_modify()
        if self.setter_type == 'simple':
            self.check_work_hour_constraints()

        main_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        self.mapped('day_schedule_ids').filtered(
            lambda d: d.work_schedule_line_id.work_schedule_id.id != main_work_schedule.id).mapped(
            'schedule_holiday_id').unlink()
        line_commands = [(5,)]
        res = {
            'line_ids': line_commands,
            'free_day': self.free_day,
            'business_trip': self.business_trip,
            'schedule_holiday_id': False
        }
        self.mapped('day_schedule_ids.work_schedule_line_id').ensure_not_busy()
        if self.free_day:
            self.day_schedule_ids.write(res)
            return

        if self.setter_type == 'simple':
            fd_zymejimas_id = self.env.ref('work_schedule.work_schedule_code_FD').id

            if self.lunch_break:
                vals_1 = {'work_schedule_code_id': fd_zymejimas_id,
                          'time_from': self.work_hours_from,
                          'time_to': self.break_hours_from}
                vals_2 = {'work_schedule_code_id': fd_zymejimas_id,
                          'time_from': self.break_hours_to,
                          'time_to': self.work_hours_to}
                line_commands.append((0, 0, vals_1))
                line_commands.append((0, 0, vals_2))
            else:
                vals = {'work_schedule_code_id': fd_zymejimas_id,
                        'time_from': self.work_hours_from,
                        'time_to': self.work_hours_to}
                line_commands.append((0, 0, vals))
        else:
            single_day = len(self.day_schedule_ids) == 1
            lines_to_add = self.env['main.setter.worked.time.line']
            if single_day:
                # Figure out which lines should be added and which ones should be kept
                day_lines = self.day_schedule_ids.line_ids
                lines_to_keep = self.env['work.schedule.day.line']
                line_commands = []
                for line in self.line_ids:
                    line_already_exists = False
                    for existing_line in day_lines:
                        match = tools.float_compare(existing_line.time_from, line.time_from, precision_digits=2) == 0 and \
                                tools.float_compare(existing_line.time_to, line.time_to, precision_digits=2) == 0 and \
                                existing_line.work_schedule_code_id == line.work_schedule_code_id
                        if match:
                            line_already_exists = True
                            lines_to_keep |= existing_line
                            break
                    if not line_already_exists:
                        lines_to_add |= line
                line_commands += [(3, day_line.id, 0) for day_line in day_lines if day_line not in lines_to_keep]
            else:
                lines_to_add = self.line_ids

            for line in lines_to_add:
                vals = {
                    'work_schedule_code_id': line.work_schedule_code_id.id,
                    'time_from': line.time_from,
                    'time_to': line.time_to,
                }
                line_commands.append((0, 0, vals))
            res['line_ids'] = line_commands
        self.day_schedule_ids.write(res)


MainScheduleSetter()