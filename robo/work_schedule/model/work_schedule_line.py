# -*- coding: utf-8 -*-
import logging
import threading
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions, SUPERUSER_ID
from odoo.api import Environment
from odoo.tools.translate import _
from odoo.addons.queue_job.job import job, identity_exact
from work_schedule import SCHEDULE_STATES
from six import iteritems

from odoo.addons.robo.models.robo_tools import MONTH_TO_STRING_MAPPING
from odoo.addons.robo.models.linksnis import kas_to_ko

_logger = logging.getLogger(__name__)


class WorkScheduleLine(models.Model):
    _name = 'work.schedule.line'

    _sql_constraints = [('work_schedule_line_department_employee_unique', 'unique(work_schedule_id, department_id, employee_id, month, year)',
                         _('Vienas darbuotojas gali turėti tik vieną eilutę viename skyriuje vienam periodui'))]

    work_schedule_id = fields.Many2one('work.schedule', string='Darbo grafikas', required=True, ondelete='cascade')

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, ondelete='cascade')
    department_id = fields.Many2one('hr.department', string='Padalinys', required=True, ondelete='cascade')

    year = fields.Integer('Metai', required=True)
    month = fields.Integer('Mėnuo', required=True)

    state = fields.Selection(SCHEDULE_STATES, string='Būsena', required=True, default='draft')
    day_ids = fields.One2many('work.schedule.day', 'work_schedule_line_id', string='Dienos')

    employee_job_id = fields.Many2one('hr.job', string='Pareigos', required=True, related='employee_id.job_id')
    current_user_department_line = fields.Boolean(compute='_compute_current_user_department_line',
                                                  search='_search_current_user_department_line')
    used_as_planned_schedule_in_calculations = fields.Boolean(string='Naudojmas darbo užmokęsčio paskaičiavimui', default=False, inverse='_set_other_departments_used_as_planned_schedule_in_calculations')
    prevent_modifying_as_past_planned = fields.Boolean(compute='_compute_prevent_modifying_as_past_planned')
    constraint_check_data = fields.Text('Data after checking constraints', default='')
    busy = fields.Boolean('Computations are running')

    @api.multi
    def _compute_prevent_modifying_as_past_planned(self):
        schedule_user_group = self.env.user.get_work_schedule_access_level()
        end_of_current_month = (datetime.utcnow() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        planned_schedule = self.env.ref('work_schedule.planned_company_schedule')
        for rec in self:
            line_date_to = (datetime(rec.year, rec.month, 1) + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if schedule_user_group <= 3 and rec.work_schedule_id == planned_schedule and \
                    end_of_current_month >= line_date_to:
                rec.prevent_modifying_as_past_planned = True

    @api.multi
    def name_get(self):
        return [
            (rec.id, '{}-{} {}-{}'.format(rec.employee_id.name, rec.department_id.name, rec.year, rec.month))
            for rec in self
        ]

    @api.multi
    @api.constrains('used_as_planned_schedule_in_calculations')
    def _check_used_as_planned_schedule_in_calculations_constraints(self):
        for rec in self.filtered('used_as_planned_schedule_in_calculations'):
            if not self.env.user.is_accountant():
                raise exceptions.ValidationError(
                    _('Neturite pakankamai teisių nustatyti grafiką atlyginimo skaičiavimui'))
            if rec.work_schedule_id.schedule_type != 'planned':
                raise exceptions.ValidationError(
                    _('Negalite nustatyti grafiko atlyginimo skaičiavimui, nes jis nėra planuojamas grafikas'))

    @api.one
    def _set_other_departments_used_as_planned_schedule_in_calculations(self):
        self.ensure_not_busy()
        employee_other_lines = self.work_schedule_id.schedule_line_ids.filtered(lambda l: l.id != self.id and l.year == self.year and l.month == self.month and l.employee_id.id == self.employee_id.id)
        for line in employee_other_lines:
            if line.used_as_planned_schedule_in_calculations != self.used_as_planned_schedule_in_calculations:
                line.write({'used_as_planned_schedule_in_calculations': self.used_as_planned_schedule_in_calculations})

    def _search_current_user_department_line(self, operator, value):
        if operator == '=' and value is True:
            user = self.env.user
            department_id = user.employee_ids[0].department_id.id if user and user.employee_ids and user.employee_ids[0].department_id else False
            if not department_id:
                department_id = self.env['hr.department'].search([], limit=1).id
            if not department_id:
                return [('current_user_department_line', operator, value)]
            same_department_line_ids = self.search([
                ('department_id', '=', department_id)
            ]).mapped('id')
            return [('id', 'in', same_department_line_ids)]
        return [('current_user_department_line', operator, value)]

    @api.one
    @api.depends('department_id')
    def _compute_current_user_department_line(self):
        user = self.env.user
        department_id = user.employee_ids[0].department_id.id if user and user.employee_ids and user.employee_ids[0].department_id else False
        if not department_id:
            department_id = self.env['hr.department'].search([], limit=1)
        if department_id.id == self.department_id.id:
            self.current_user_department_line = True

    @api.multi
    def has_access_rights_to_modify(self):
        is_manager = self.env.user.is_schedule_manager()
        is_super = self.env.user.is_schedule_super()
        has_access_rights = False
        if is_super:
            has_access_rights = True
        elif is_manager:
            line_department_ids = self.mapped('department_id.id')
            user_department_ids = self.env.user.mapped('employee_ids.department_id.id')
            has_access_rights = not any(line_department_id not in user_department_ids for line_department_id in line_department_ids)
        else:
            fill_department_ids = self.env.user.mapped('employee_ids.fill_department_ids.id')
            if fill_department_ids:
                line_department_ids = self.mapped('department_id.id')
                has_access_rights = not any(line_department_id not in fill_department_ids for line_department_id in line_department_ids)
            if not has_access_rights:
                employee_ids = self.mapped('employee_id')
                user_employee_ids = self.env.user.mapped('employee_ids')
                all_are_user_employees = not any(line_employee not in user_employee_ids for line_employee in employee_ids)
                all_can_fill_own_schedule = not any(not line_employee.sudo().can_fill_own_schedule for line_employee in employee_ids)
                has_access_rights = all_are_user_employees and all_can_fill_own_schedule

        return has_access_rights

    @api.model
    def go_to_ziniarastis(self, year, month):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Operacija neleidžiama, nes neturite buhalterio teisių'))
        try:
            date_from = datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (datetime(year,month,1)+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except:
            raise exceptions.UserError(_('Nenumatyta sistemos klaida, prašome perkrauti puslapį.'))
        ziniarastis = self.env['ziniarastis.period'].search(
            [('date_from', '>=', date_from),
             ('date_to', '<=', date_to)]).id

        if ziniarastis:
            action = self.env.ref('l10n_lt_payroll.action_ziniarastis')
            view_id = self.env.ref('l10n_lt_payroll.ziniarastis_period_form')
            menu_id = self.env.ref('l10n_lt_payroll.meniu_ziniarastis_period').id
            all_ziniarastis_ids = self.env['ziniarastis.period'].search([], order='date_from asc').mapped('id')
            current_index = all_ziniarastis_ids.index(ziniarastis)
            return {
                'id': action.id,
                'name': action.name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'ziniarastis',
                'res_model': 'ziniarastis.period',
                'views': [[view_id.id, 'ziniarastis']],
                'view_id': view_id.id,
                'res_id': ziniarastis,
                'context': {
                    'force_back_menu_id': menu_id,
                    'dataset_ids': all_ziniarastis_ids,
                    'dataset_index': current_index
                }
            }
        else:
            raise exceptions.UserError(_('Šio periodo žiniaraštis dar nesukurtas, pirmiausia sukurkite žiniaraštį.'))

    @api.multi
    def get_button_statuses(self):
        res = {
            'allow_validate': False,
            'allow_confirm': False,
            'allow_done': False,
            'allow_cancel_validate': False,
            'allow_cancel_confirm': False,
            'allow_cancel_done': False,
            'allow_go_to_ziniarastis': False,
            'allow_accountant_can_change': False,
            'allow_accountant_cant_change': False,
            'allow_go_to_date': True,
            'allow_check_constraints': False,
            'allow_check_failed_constraints': False,
            'allow_submit_all_to_accountants': False,
            'allow_set_all_as_unused': False,
            'allow_set_all_as_used': False
        }
        lines = self
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule').id
        if lines and self.env.user.is_accountant() and planned_work_schedule in lines.mapped('work_schedule_id.id'):
            res['allow_set_all_as_unused'] = any(line.used_as_planned_schedule_in_calculations for line in lines)
            res['allow_set_all_as_used'] = any(not line.used_as_planned_schedule_in_calculations for line in lines)
        if lines:
            year = list(set(lines.mapped('year')))[0]
            month = list(set(lines.mapped('month')))[0]
            work_schedule = lines.mapped('work_schedule_id')[0]
            curr_month_start = datetime.utcnow() + relativedelta(day=1)
            self_month_start = datetime(year, month, 1)
            if self_month_start <= curr_month_start and work_schedule.schedule_type == 'planned':
                res['allow_go_to_ziniarastis'] = True
                return res

        distinct_states = set(lines.mapped('state'))

        department_ids = self.mapped('department_id')
        validate_department_ids = self.env.user.mapped('employee_ids.validate_department_ids')
        confirm_department_ids = self.env.user.mapped('employee_ids.confirm_department_ids')
        user_can_validate = any(department_id in validate_department_ids for department_id in department_ids)
        user_can_confirm = any(department_id in confirm_department_ids for department_id in department_ids)

        if self.env.user.is_schedule_manager() or user_can_validate:
            res['allow_check_constraints'] = True
            res['allow_check_failed_constraints'] = lines.sudo().get_failed_constraint_string() != ''
            if self.env.user.company_id.schedule_policy == 'two_step':
                res['allow_validate'] = 'draft' in distinct_states
                res['allow_cancel_validate'] = 'validated' in distinct_states
        if self.env.user.is_schedule_super() or user_can_confirm:
            res['allow_confirm'] = 'validated' in distinct_states
            res['allow_cancel_confirm'] = 'confirmed' in distinct_states
            res['allow_submit_all_to_accountants'] = any(ds in ['draft', 'validated'] for ds in distinct_states)
        if self.env.user.is_accountant():
            res['allow_go_to_ziniarastis'] = True
            res['allow_done'] = 'confirmed' in distinct_states
            res['allow_cancel_done'] = 'done' in distinct_states

        return res

    @api.model
    def action_toggle_allow_accountant_change(self, year, month):
        if not year or not month:
            raise exceptions.ValidationError(_('Nenumatyta klaida, neįmanoma nustatyti grafiko datos'))
        try:
            year = int(year)
            month = int(month)
        except:
            raise exceptions.ValidationError(_('Nenumatyta klaida, grafiko data neatitinka formato'))
        if not self.env.user.has_group('robo_basic.group_robo_premium_chief_accountant'):
            raise exceptions.UserError(_('Operacija neleidžiama, tik vyr. buhalteriai gali įjungti grafikų keitimą'))

        department_lines = self.search([
            ('year', '=', year),
            ('month', '=', month)
        ])
        if not department_lines:
            return
        department_lines.ensure_not_busy()

    @api.multi
    def action_check_constraints(self):
        lines = self
        if not self.env.user.is_schedule_manager():
            fill_department_ids = self.env.user.mapped('employee_ids.fill_department_ids')
            validate_department_ids = self.env.user.mapped('employee_ids.validate_department_ids')
            confirm_department_ids = self.env.user.mapped('employee_ids.confirm_department_ids')
            departments_user_can_check = fill_department_ids + validate_department_ids + confirm_department_ids
            lines = self.filtered(lambda s: s.department_id in departments_user_can_check or (s.employee_id.id in self.env.user.employee_ids.ids and s.employee_id.sudo().can_fill_own_schedule))
            if not lines:
                raise exceptions.UserError(_('Operacija neleidžiama, nes neturite teisės peržiūrėti grafikų apribojumus'))
        return lines.sudo().check_line_constraints_and_execute_action_after(raise_on_success=True)

    @api.model
    def check_work_schedule_manager_rights(self):
        if not self.env.user.is_schedule_manager():
            if not self.env.user.can_validate_schedule_departments(self.mapped('department_id.id')):
                raise exceptions.UserError(_('Operacija neleidžiama, nes neturite teisės keisti grafiko būsenos'))

    @api.model
    def check_work_schedule_super_rights(self):
        if not self.env.user.is_schedule_super():
            if not self.env.user.can_confirm_schedule_departments(self.mapped('department_id.id')):
                raise exceptions.UserError(_('Operacija neleidžiama, nes neturite teisės atlikti tolimesnius grafiko '
                                             'pakeitimus'))

    @api.multi
    def check_holidays_are_confirmed(self):
        err_msg = ''
        single_hol_str = _('Negalima patvirtinti darbuotojo %s grafiko, nes nerasti neatvykimų įrašai patvirtinantys šiuos '
                           'grafiko neatvykimus:\n')
        ignore_holidays = ['PK']
        related_holidays = self.mapped('day_ids.schedule_holiday_id')
        unconfirmed_holidays = related_holidays.filtered(lambda h: not h.is_confirmed
                                                                   and h.holiday_status_id.kodas not in ignore_holidays)
        for employee_id in unconfirmed_holidays.mapped('employee_id'):
            if err_msg != '':
                err_msg += '\n\n'
            employee_holidays = unconfirmed_holidays.filtered(lambda h: h.employee_id.id == employee_id.id)
            err_msg += single_hol_str % employee_id.name
            index = 1
            for empl_hol in employee_holidays:
                err_msg += '%d.%s (%s - %s)\n' % (index, empl_hol.holiday_status_id.display_name, empl_hol.date_from, empl_hol.date_to)
                index += 1

        # Special case for truancy - days might not have related schedule holiday id
        truancy_day_data = self.mapped('day_ids.line_ids').filtered(lambda l: l.code == 'PB').mapped('day_id').read(
            ['employee_id', 'date']
        )
        if truancy_day_data:
            employee_ids = [x['employee_id'][0] for x in truancy_day_data]
            dates = [x['date'] for x in truancy_day_data]
            truancy_holiday_data = self.env['hr.holidays'].search([
                ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_PB').id),
                ('employee_id', 'in', employee_ids),
                ('date_from_date_format', '<=', max(dates)),
                ('date_to_date_format', '>=', min(dates)),
                ('state', '=', 'validate'),
                ('type', '=', 'remove')
            ]).read(['employee_id', 'date_from_date_format', 'date_to_date_format'])
            for truancy_day in truancy_day_data:
                employee_data = truancy_day['employee_id']
                employee_id, employee_name, date = employee_data[0], employee_data[1], truancy_day['date']
                has_related_holiday = any(
                    h['employee_id'][0] == employee_id and h['date_from_date_format'] <= date <= h['date_to_date_format']
                    for h in truancy_holiday_data
                )
                if not has_related_holiday:
                    err_msg += _('Trūksta darbuotojo {} pravaikštos akto datai {}\n').format(employee_name, date)

        return err_msg

    @api.multi
    @api.constrains('state')
    def prevent_planned_schedule_state_changes(self):
        if not self._context.get('bypass_state_change'):
            curr_month_start = datetime.utcnow() + relativedelta(day=1)
            planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
            for rec in self:
                self_month_start = datetime(rec.year, rec.month, 1)
                self_is_planned_schedule = rec.work_schedule_id.id == planned_work_schedule.id
                if self_month_start <= curr_month_start and self_is_planned_schedule:
                    raise exceptions.UserError(_('Negalima keisti suplanuoto grafiko būsenos'))

    @api.model
    def is_schedule_super(self):
        return self.env.user.is_schedule_super()

    @api.model
    def no_lines_error(self):
        if not self.env.user.is_schedule_super():
            raise exceptions.UserError(_('Nei viena iš pasirinktų eilučių nepriklauso jūsų padaliniui, todėl negalite '
                                         'keisti šių eilučių būsenos'))
        else:
            raise exceptions.UserError(_('Nėra eilučių, kurias būtų galima keisti'))

    @api.multi
    def ensure_not_busy(self):
        if self._context.get('automatic_payroll', False):
            return
        if any(rec.busy for rec in self):
            raise exceptions.ValidationError(_('Šiuo metu tikrinami eilučių apribojimai. Prašome palaukti.'))
        date_data = [(rec.year, rec.month) for rec in self]
        date_data = list(set(date_data))
        HrPayroll = self.env['hr.payroll']
        payrolls = HrPayroll.search([])
        for date_range in date_data:
            period_payroll = payrolls.filtered(lambda p: p.year == date_range[0] and p.month == date_range[1])
            if not period_payroll:
                period_payroll = HrPayroll.sudo().create({
                    'year': date_range[0], 'month': date_range[1]
                })
            elif len(period_payroll) > 1:
                period_payroll = period_payroll[0]
            if period_payroll.busy:
                raise exceptions.ValidationError(_('Šiuo metu vykdomas atlyginimų skaičiavimas, todėl negalite atlikti '
                                                   'šio veiksmo'))

    @api.multi
    def get_lines_to_validate(self):
        is_schedule_super = self.is_schedule_super()
        user_employees = self.env.user.mapped('employee_ids')
        user_department_ids = user_employees.mapped('department_id').ids + \
                              user_employees.mapped('validate_department_ids').ids

        lines_to_validate = self
        if not is_schedule_super:
            lines_to_validate = lines_to_validate.filtered(lambda l: l.department_id.id in user_department_ids)
        lines_to_validate = lines_to_validate.filtered(lambda l: l.state == 'draft' and not l.busy)
        return lines_to_validate

    @api.model
    def should_check_constraints_on_action(self, action='validate'):
        user = self.env.user
        company = user.sudo().company_id
        allow_bypass_constraints = company.work_schedule_labour_code_bypass == 'allowed'
        should_check_constraint_on_this_action = company.work_schedule_state_to_check_constraints == action
        return should_check_constraint_on_this_action and not allow_bypass_constraints and not user.is_accountant()

    @api.multi
    def action_validate(self):
        self.check_work_schedule_manager_rights()
        self.ensure_not_busy()

        lines_to_validate = self.get_lines_to_validate()
        if not lines_to_validate:
            self.no_lines_error()

        # Check if the constraints should be checked
        if self.should_check_constraints_on_action(action='validate'):
            missing_employee_warning = lines_to_validate.get_related_missing_employees_warning()
            if missing_employee_warning != '':
                raise exceptions.ValidationError(missing_employee_warning)
            return lines_to_validate.check_line_constraints_and_execute_action_after(action_after='validate')

        return lines_to_validate.finalise_validation()

    @api.multi
    def finalise_validation(self):
        """ Finalises line validation. Assumes user rights were checked before. """
        # Find lines to validate
        lines_to_validate = self
        if not self._context.get('ignore_busy'):
            lines_to_validate = self.filtered(lambda l: not l.busy)
        if not lines_to_validate:
            return

        # Log user action
        _logger.info('User ID:{} attempting to validate work schedule lines ({})'.format(
            self.env.user.id, ', '.join(str(x) for x in self.ids))
        )

        # Write values on lines
        vals = {'state': 'validated'}
        if not self.env.user.is_schedule_super():
            validate_department_ids = self.env.user.mapped('employee_ids').mapped('validate_department_ids').ids
            lines_to_validate.filtered(
                lambda l: l.department_id.id in validate_department_ids
            ).sudo().write(vals)
            lines_to_validate.filtered(
                lambda l: l.department_id.id not in validate_department_ids
            ).write(vals)
        else:
            lines_to_validate.write(vals)
        self.inform_employees_about_schedule_changes()
        if self.env.user.company_id.schedule_policy == 'one_step':
            lines_to_validate.filtered(lambda l: l.state == 'validated').action_confirm()

    @api.multi
    def inform_employees_about_schedule_changes(self):
        company = self.env.user.company_id
        if company.inform_employees_about_schedule_changes == 'inform':
            schedule_for_tracking_changes = self.env.ref('work_schedule.track_latest_schedule_changes_schedule')
            line_periods = set([(line.year, line.month) for line in self])
            now = datetime.utcnow()
            current_year, current_month = now.year, now.month
            for period in line_periods:
                year, month = period
                if current_year > year or (current_year == year and current_month > month):
                    continue
                period_lines = self.filtered(lambda l: l.year == year and l.month == month)
                backup_lines = schedule_for_tracking_changes.sudo().schedule_line_ids.filtered(lambda l:
                    l.year == line.year and
                    l.month == line.month
                )
                employees = period_lines.mapped('employee_id')
                for employee in employees:
                    email = employee.sudo().address_home_id.email
                    if not email or not employee.user_id:
                        continue

                    employee_lines = period_lines.filtered(lambda l: l.employee_id == employee)
                    employee_days = employee_lines.mapped('day_ids')
                    line_departments = employee_lines.mapped('department_id')
                    employee_backup_lines = backup_lines.filtered(lambda l: l.employee_id == employee and
                                                                            l.department_id.id in line_departments.ids)
                    backup_days = employee_backup_lines.mapped('day_ids')
                    changes_exist = False
                    if not backup_days:
                        existing_confirmed_schedule_lines = self.env['work.schedule.line'].sudo().search_count([
                            ('year', '=', year),
                            ('month', '=', month),
                            ('employee_id', '=', employee.id),
                            ('department_id', 'not in', line_departments.ids),
                            ('state', '!=', 'draft')
                        ])
                        if not existing_confirmed_schedule_lines:
                            continue
                        work_time_has_been_set = not tools.float_is_zero(
                            sum(employee_days.mapped('line_ids.worked_time_total')),
                            precision_digits=2
                        )
                        if work_time_has_been_set:
                            # A new line has just been validated but there's other validated lines already meaning that
                            # the employee might have seen the other lines but there's some work time in these lines
                            # that the employee should know about
                            changes_exist = True
                    else:
                        dates = list(set(employee_days.mapped('date') + backup_days.mapped('date')))
                        for date in dates:
                            date_actual_times = employee_days.filtered(lambda d: d.date == date).mapped('line_ids').sorted(
                                lambda l: l.time_from
                            )
                            date_backup_times = backup_days.filtered(lambda d: d.date == date).mapped('line_ids').sorted(
                                lambda l: l.time_from
                            )
                            number_of_time_lines = len(date_actual_times)
                            if number_of_time_lines != len(date_backup_times):
                                changes_exist = True
                                break
                            for i in range(0, number_of_time_lines):
                                # Since they are sorted by time from everything should match. If something does not - we
                                # inform the employee
                                actual_time = date_actual_times[i]
                                date_backup_time = date_backup_times[i]
                                if tools.float_compare(actual_time.time_from, date_backup_time.time_from, precision_digits=2) != 0 or \
                                    tools.float_compare(actual_time.time_to, date_backup_time.time_to, precision_digits=2) != 0 or \
                                    actual_time.work_schedule_code_id != date_backup_time.work_schedule_code_id or \
                                    actual_time.department_id != date_backup_time.department_id:
                                    changes_exist = True
                                    break
                            if changes_exist:
                                break
                    if changes_exist:
                        url = 'https://{0}.robolabs.lt/web?#view_type=workschedule&robo_menu_id={1}&model=' \
                              'work.schedule.line&menu_id={1}&action={2}'.format(
                            self.env.cr.dbname,
                            self.env.ref('work_schedule.menu_work_schedule_main').id,
                            self.env.ref('work_schedule.action_main_work_schedule_view').id,
                        )
                        msg_body = _('''
                        Sveiki,
                        jūsų {} m. {} mėn. grafikas Robo platformoje buvo pakeistas.\n\n
                        <a href=\"{}\" style=\"padding: 8px 12px; font-size: 12px; color: #FFFFFF; 
                        text-decoration: none !important; font-weight: 400; background-color: #3498DB; 
                        border: 0px solid #3498DB; border-radius:3px; margin-top: 10px;\">Atidaryti</a>\n
                        ''').format(
                            year,
                            kas_to_ko(MONTH_TO_STRING_MAPPING.get(month)),
                            url
                        )
                        msg_subject = _('Jūsų darbo grafikas buvo pakeistas')
                        self.env['script'].sudo().send_email(emails_to=[email],
                                                      subject=msg_subject,
                                                      body=msg_body)

    @api.multi
    def action_cancel_validate(self):
        self.check_work_schedule_manager_rights()
        self.ensure_not_busy()
        is_schedule_super = self.is_schedule_super()
        validate_department_ids = self.env.user.mapped('employee_ids.validate_department_ids.id')
        user_departments = self.env.user.mapped('employee_ids.department_id.id') + validate_department_ids
        lines_to_validate = self
        if not is_schedule_super:
            lines_to_validate = lines_to_validate.filtered(lambda l: l.department_id.id in user_departments)
        lines_to_validate = lines_to_validate.filtered(lambda l: l.state == 'validated')
        if not lines_to_validate:
            self.no_lines_error()
        lines_to_validate.filtered(lambda l: l.department_id.id in validate_department_ids).sudo().write({'state': 'draft'})
        lines_to_validate.filtered(lambda l: l.department_id.id not in validate_department_ids).write({'state': 'draft'})
        if self.should_check_constraints_on_action('validate'):
            lines_to_validate.sudo().write({'constraint_check_data': ''})

        company = self.sudo().env.user.company_id
        if company.inform_employees_about_schedule_changes == 'inform':
            schedule_for_tracking_changes = self.env.ref('work_schedule.track_latest_schedule_changes_schedule')
            existing_backup_lines = schedule_for_tracking_changes.sudo().schedule_line_ids

            # Unlink all already existing lines
            line_data = [(line.year, line.month, line.employee_id, line.department_id) for line in lines_to_validate]
            line_data = set(line_data)
            existing_lines_to_unlink = self.env['work.schedule.line']
            for data in line_data:
                existing_lines_to_unlink |= existing_backup_lines.filtered(
                    lambda l:
                    l.year == data[0] and
                    l.month == data[1] and
                    l.employee_id == data[2] and
                    l.department_id == data[3]
                )
            existing_lines_to_unlink.sudo().unlink()

            for line in lines_to_validate:
                # Copy line, days and day lines
                backup_line = line.sudo().copy({'work_schedule_id': schedule_for_tracking_changes.id})
                for day in line.day_ids:
                    backup_day = day.sudo().with_context(no_raise=True).copy({'work_schedule_line_id': backup_line.id})
                    day_lines = day.sudo().line_ids
                    for day_line in day_lines:
                        day_line.copy({'day_id': backup_day.id})

    @api.multi
    def action_confirm(self):
        self.check_work_schedule_super_rights()
        self.ensure_not_busy()

        lines_to_confirm = self.filtered(lambda l: l.state == 'validated')
        if not self._context.get('ignore_busy'):
            lines_to_confirm = self.filtered(lambda l: not l.busy)
        if not lines_to_confirm:
            self.no_lines_error()

        if self.should_check_constraints_on_action('confirm'):
            missing_employee_warning = lines_to_confirm.get_related_missing_employees_warning()
            if missing_employee_warning != '':
                raise exceptions.ValidationError(missing_employee_warning)
            return lines_to_confirm.check_line_constraints_and_execute_action_after(action_after='confirm')

        return lines_to_confirm.finalise_confirmation()

    @api.multi
    def finalise_confirmation(self):
        """ Finalises confirming lines. Assumes user rights were checked before. """
        # Get lines to confirm
        lines_to_confirm = self
        if not self._context.get('ignore_busy'):
            lines_to_confirm = self.filtered(lambda l: not l.busy)
        if not lines_to_confirm:
            return

        # Log user action
        _logger.info('User ID:{} attempting to confirm work schedule lines ({})'.format(
            self.env.user.id, ', '.join(str(x) for x in self.ids))
        )

        # Write values to departments where that the user can confirm as super user and to other departments as regular
        vals = {'state': 'confirmed'}
        confirm_department_ids = self.env.user.mapped('employee_ids.confirm_department_ids').ids
        lines_to_confirm.filtered(lambda l: l.department_id.id in confirm_department_ids).sudo().write(vals)
        lines_to_confirm.filtered(lambda l: l.department_id.id not in confirm_department_ids).write(vals)
        self.inform_about_confirmed_schedule_for_last_month(lines_to_confirm)

    @api.model
    def inform_about_confirmed_schedule_for_last_month(self, lines):
        """
        Method to email the accountant if work schedule lines for the previous month have all been confirmed;
        """
        if not lines:
            return
        previous_month_date = datetime.utcnow() - relativedelta(month=1)
        lines_factual_previous_month = lines.filtered(
            lambda line: line.year == previous_month_date.year and line.month == previous_month_date.month and
                         line.work_schedule_id.schedule_type == 'factual')
        if not lines_factual_previous_month:
            return
        unconfirmed_lines_previous_month = self.env['work.schedule.line'].search_count([
            ('work_schedule_id.schedule_type', '=', 'factual'),
            ('state', 'in', ['draft', 'validated']),
            ('year', '=', previous_month_date.year),
            ('month', '=', previous_month_date.month),
        ])

        if unconfirmed_lines_previous_month:
            return

        subject = '[{}] Pateikti darbuotojų grafikai {}-{} laikotarpiui'.format(
            self.env.cr.dbname, previous_month_date.year, previous_month_date.month)
        body = 'Visi įmonės darbuotojų grafikai {} metų {} mėn. buvo pateikti. Patvirtinkite juos.'.format(
            previous_month_date.year, previous_month_date.month)

        findir_email = self.sudo().env.user.company_id.findir.partner_id.email
        if findir_email:
            self.env['script'].sudo().send_email(emails_to=[findir_email], subject=subject, body=body)

    @api.multi
    def action_cancel_confirm(self):
        self.check_work_schedule_super_rights()
        self.ensure_not_busy()

        lines_to_validate = self.filtered(lambda l: l.state == 'confirmed' and not l.busy)
        if not lines_to_validate:
            self.no_lines_error()

        confirm_department_ids = self.env.user.mapped('employee_ids.confirm_department_ids.id')
        vals = {'state': 'validated'}
        lines_to_validate.filtered(lambda l: l.department_id.id in confirm_department_ids).sudo().write(vals)
        lines_to_validate.filtered(lambda l: l.department_id.id not in confirm_department_ids).write(vals)
        if self.should_check_constraints_on_action('confirm'):
            lines_to_validate.sudo().write({'constraint_check_data': ''})

        if self.env.user.company_id.schedule_policy == 'one_step':
            self.search([('state', '=', 'validated')]).action_cancel_validated()

    @api.multi
    def action_done(self):
        self.ensure_not_busy()
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('This action can only be performed by accountants!'))
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule').id

        if not self._context.get('execute_in_thread'):
            for year in set(self.mapped('year')):
                for month in set(self.filtered(lambda l: l.year == year).mapped('month')):
                    month_lines = self.filtered(lambda l: l.year == year and l.month == month and not l.busy)
                    for employee in month_lines.mapped('employee_id.id'):
                        employee_month_lines = month_lines.filtered(lambda l: l.employee_id.id == employee)
                        if len(set(employee_month_lines.mapped('work_schedule_id.id'))) == 1 and (
                                datetime(year, month, 1) <= datetime.utcnow() or employee_month_lines[
                            0].work_schedule_id.id != planned_work_schedule):
                            employee_month_lines.write({'state': 'done'})
                            employee_month_lines.action_generate_ziniarasciai_for_department_lines()
                        else:
                            for line in employee_month_lines:
                                if datetime(year, month,
                                            1) <= datetime.utcnow() or line.work_schedule_id != planned_work_schedule:
                                    line.write({'state': 'done'})
                                    line.action_generate_ziniarasciai_for_department_lines()
        else:
            lines = self.filtered(lambda l: l.state != 'done' and not l.busy)
            threaded_calculation = threading.Thread(target=self.action_done_threaded, args=(lines.ids,))
            threaded_calculation.start()

    @api.model
    def action_done_threaded(self, work_schedule_line_ids):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})

            planned_work_schedule = env.ref('work_schedule.planned_company_schedule')

            now = datetime.utcnow()

            work_schedule_lines = env['work.schedule.line'].browse(work_schedule_line_ids)
            periods = set((l.year, l.month) for l in work_schedule_lines)
            for (year, month) in periods:
                current_or_previous_period = datetime(year, month, 1) <= now

                payroll = env['hr.payroll'].search([('year', '=', year), ('month', '=', month)], limit=1)
                if not payroll:
                    payroll = env['hr.payroll'].create({'year': year, 'month': month})
                payroll.write({'busy': True, 'partial_calculations_running': True, 'stage': 'schedule'})

                period_lines = work_schedule_lines.filtered(lambda l: l.year == year and l.month == month)
                employees = period_lines.mapped('employee_id')

                new_cr.commit()
                try:
                    employee_based_cr = self.pool.cursor()
                    employee_based_env = api.Environment(employee_based_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
                    history_obj = employee_based_env['automatic.payroll.execution.history'].create({
                        'year': year,
                        'month': month
                    })
                    for employee in employees:
                        employee_based_cr.commit()
                        exception_message = None
                        try:
                            employee_lines = period_lines.filtered(lambda l: l.employee_id == employee)
                            employee_lines = employee_based_env['work.schedule.line'].browse(employee_lines.ids)
                            for line in employee_lines:
                                if line.state == 'done':
                                    continue
                                if current_or_previous_period or line.work_schedule_id != planned_work_schedule:
                                    line.with_context(automatic_payroll=True).write({'state': 'done'})
                                    line.with_context(automatic_payroll=True).action_generate_ziniarasciai_for_department_lines()
                        except Exception as e:
                            exception_message = e.args[0] if e.args else e.message
                            employee_based_cr.rollback()
                        finally:
                            employee_based_env['automatic.payroll.execution.employee.history'].create({
                                'history_obj_id': history_obj.id,
                                'message': exception_message if exception_message else '',
                                'stage': 'schedule',
                                'employee_id': employee.id,
                                'success': not bool(exception_message),
                            })
                            employee_based_cr.commit()
                    employee_based_cr.close()
                except Exception as e:
                    raise e
                finally:
                    payroll.write({'busy': False, 'partial_calculations_running': False, 'stage': False})
                    new_cr.commit()
            new_cr.close()

    @api.multi
    def action_generate_ziniarasciai_for_department_lines(self):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Operacija neleidžiama, nes neturite teisės kurti žiniaraščių'))
        self.ensure_not_busy()
        period_lines_to_update = self.env['ziniarastis.period.line']
        periods = set((l.year, l.month) for l in self)
        for (year, month) in periods:
            first_of_month = datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            last_of_month = (datetime(year, month, 1)+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            period_lines = self.filtered(lambda l: l.year == year and l.month == month)

            ziniarastis = self.env['ziniarastis.period'].search([
                ('date_from', '=', first_of_month),
                ('date_to', '=', last_of_month)
            ], limit=1)
            if ziniarastis and ziniarastis.state != 'draft':
                continue
            elif not ziniarastis:
                ziniarastis = self.env['ziniarastis.period'].create({
                    'date_from': first_of_month,
                    'date_to': last_of_month
                })

            employees = period_lines.mapped('employee_id')
            contracts = self.env['hr.contract'].search([
                ('employee_id', 'in', employees.ids),
                ('date_start', '<=', last_of_month),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', first_of_month)
            ])

            period_lines = self.env['ziniarastis.period.line'].search([
                ('contract_id', 'in', contracts.ids),
                ('date_from', '=', first_of_month),
                ('date_to', '=', last_of_month),
            ])
            for contract in contracts:
                period_line = period_lines.filtered(lambda l: l.contract_id == contract)
                if period_line and period_line.state != 'draft':
                    continue
                elif not period_line:
                    period_line = self.env['ziniarastis.period.line'].create({
                        'ziniarastis_period_id': ziniarastis.id,
                        'employee_id': contract.employee_id.id,
                        'contract_id': contract.id,
                        'date_from': ziniarastis.date_from,
                        'date_to': ziniarastis.date_to,
                        'working_schedule_number': contract.working_schedule_number
                    })
                period_lines_to_update |= period_line
        period_lines_to_update.filtered(lambda r: r['state'] != 'done').auto_fill_period_line()

    @api.multi
    def action_cancel_done(self):
        # TODO we should add a parameter to either raise error or continue
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Tik buhalteriai gali atlikti šią operaciją'))
        self.ensure_not_busy()
        for line in self.filtered(lambda l: l.state == 'done' and not l.busy):
            date_from = datetime(line.year, line.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (datetime(line.year, line.month, 1)+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            confirmed_ziniarastis_period_lines = self.env['ziniarastis.period.line'].search_count([
                ('employee_id', '=', line.employee_id.id),
                ('date_from', '=', date_from),
                ('date_to', '=', date_to),
                ('state', '!=', 'draft')
            ])
            if confirmed_ziniarastis_period_lines > 0:
                raise exceptions.UserError(_('Susijusi žiniaraščio eilutė jau patvirtinta, norėdami atšaukti - '
                                             'pirmiausia atšaukite žiniaraščio eilutę (%s)') % line.employee_id.display_name)
            else:
                line.write({'state': 'confirmed'})

    @api.multi
    def action_set_all_as_used_or_not(self, value_to_set):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Tik buhalteriai gali atlikti šią operaciją'))
        self.ensure_not_busy()
        self.write({'used_as_planned_schedule_in_calculations': value_to_set})

    @api.model
    def execute_multiple_line_action(self, action, year, month, extra_domain=False, work_schedule_id=None):
        domain = [('year', '=', year), ('month', '=', month)]
        first_of_month = datetime(year, month, 1)
        planned_work_schedule = self.env.ref('work_schedule.planned_company_schedule')
        factual_work_schedule = self.env.ref('work_schedule.factual_company_schedule')

        if not work_schedule_id or not self.env.user.is_accountant():
            if datetime.utcnow() <= first_of_month:
                work_schedule_id = planned_work_schedule.id
            else:
                work_schedule_id = factual_work_schedule.id

        domain.append(('work_schedule_id.id', '=', work_schedule_id))

        if extra_domain:
            for domain_element in extra_domain:
                if domain_element in ['|', '&']:
                    domain.append(domain_element)
                else:
                    domain.append(tuple(domain_element))
        lines = self.search(domain)

        if not lines:
            return
        if action != 'call_check_constraints':
            lines.ensure_not_busy()
        if action == 'call_check_constraints':
            return lines.action_check_constraints()
        elif action == 'call_set_validated':
            lines.action_validate()
        elif action == 'call_set_confirmed':
            lines.action_confirm()
        elif action == 'call_set_done':
            lines.with_context(execute_in_thread=True).action_done()
        elif action == 'call_cancel_validated':
            lines.action_cancel_validate()
        elif action == 'call_cancel_confirmed':
            lines.action_cancel_confirm()
        elif action == 'call_cancel_done':
            lines.action_cancel_done()
        elif action == 'call_set_all_as_used':
            lines.action_set_all_as_used_or_not(True)
        elif action == 'call_set_all_as_unused':
            lines.action_set_all_as_used_or_not(False)
        elif action == 'call_check_failed_constraints':
            lines.show_failed_line_constraints()
        else:
            raise exceptions.UserError(_('Nenumatyta klaida, prašome perkrauti puslapį.'))

    @api.multi
    def unlink(self):
        if any(rec.prevent_modifying_as_past_planned for rec in self):
            raise exceptions.ValidationError(_('You can not modify confirmed planned schedule lines'))

        if not self.env.user.is_schedule_super():
            for rec in self:
                if rec.department_id.id in self.env.user.mapped('employee_ids.fill_department_ids.id') or \
                        rec.employee_id.sudo().can_fill_own_schedule and rec.employee_id.id in self.env.user.employee_ids.ids:
                    super(WorkScheduleLine, rec.sudo()).unlink()
                else:
                    super(WorkScheduleLine, rec).unlink()
        else:
            super(WorkScheduleLine, self).unlink()

    @api.multi
    def get_related_missing_employees_warning(self):
        """ Finds related missing employees based on the schedule lines provided"""

        def generate_key_set(line):
            return line.year, line.month, line.work_schedule_id  # Returns a key to group lines by

        def generate_key_domain(key):
            # Builds an ORM domain from key. Should match item order of elements returned by generate_key_set.
            return [('year', '=', key[0]), ('month', '=', key[1]), ('work_schedule_id', '=', key[2].id)]

        warning = ''
        for lines_period_key in list(set(generate_key_set(line) for line in self)):
            # Get lines for a specific period and one specific work schedule
            lines_by_key = self.filtered(lambda l, key=lines_period_key: generate_key_set(l) == key)

            departments = None  # Check all departments

            # Find all other lines of this period
            related_lines_domain = generate_key_domain(lines_period_key)
            related_lines_domain.append(('id', 'not in', lines_by_key.ids))
            related_lines = self.sudo().search(related_lines_domain)

            if related_lines:
                # If there's still some other related lines with the same or lower state then departments to check
                # should be set.
                ordered_schedule_states = [s[0] for s in SCHEDULE_STATES]
                lowest_state_of_key = min(ordered_schedule_states.index(line.state) for line in lines_by_key)
                lowest_related_state = min(ordered_schedule_states.index(line.state) for line in related_lines)
                if lowest_related_state <= lowest_state_of_key:
                    departments = lines_by_key.mapped('department_id')

            # Get missing employee warning for the provided period
            warning += self.env['work.schedule'].perform_missing_employee_validation(
                year=lines_period_key[0], month=lines_period_key[1], work_schedule=lines_period_key[2],
                departments=departments
            )

        return warning

    @api.multi
    def check_line_constraints_and_execute_action_after(self, action_after=None, raise_on_success=False):
        """ Checks constraints for multiple lines at once. Uses jobs if there's a lot of lines to check """
        # Only check the lines that are not validated or are not currently checked by another thread
        lines_not_busy = self.filtered(lambda l: not l.busy)

        use_jobs = len(lines_not_busy) > 5  # Use jobs if there are more than 5 lines to check

        check_holiday_records = not self._context.get('skip_holiday_record_checks', False)

        origin_uid = self.env.user.id

        args = (action_after, check_holiday_records)
        kwargs = {'original_user_id': origin_uid}
        job_kwargs = dict(eta=5, channel='root', identity_key=identity_exact, priority=1)

        with Environment.manage():
            # Open a new cursor for lines to check
            new_cr = self.pool.cursor()
            context = self.env.context.copy()
            env = api.Environment(new_cr, origin_uid, context)
            lines_to_check = env['work.schedule.line'].browse(lines_not_busy.ids)

            # Set the lines as being checked
            lines_to_check.sudo().write({'busy': True})
            env.cr.commit()

            for line in lines_to_check:
                if use_jobs:
                    line.with_delay(**job_kwargs).check_and_update_breached_line_constraints(*args, **kwargs)
                else:
                    line.check_and_update_breached_line_constraints(*args, **kwargs)

            env.cr.commit()
            env.cr.close()

        if use_jobs:
            return self.env.ref('work_schedule.action_show_constraints_are_being_checked_notification').read()[0]
        else:
            lines_not_busy.show_failed_line_constraints(raise_on_success)

    @api.multi
    @job
    def check_and_update_breached_line_constraints(self, action_after=None, check_holiday_records=False,
                                                   original_user_id=None):
        self.ensure_one()

        with Environment.manage():
            try:
                new_cr = self.pool.cursor()
                context = self.env.context.copy()
                user_id = original_user_id or self.env.user.id
                env = api.Environment(new_cr, user_id, context)
                line = env['work.schedule.line'].browse(self.id)

                # Check the line constraints and store them
                errors = ''
                if line.constraint_check_data != 'VALID':
                    errors += line.check_line_constraints()
                if check_holiday_records:
                    errors += line.check_holidays_are_confirmed()
                has_errors = errors != ''
                line.sudo().write({'constraint_check_data': errors if has_errors else 'VALID'})

                if has_errors:
                    # Skip finalisation actions
                    line.sudo().write({'busy': False})
                    env.cr.commit()
                    env.cr.close()
                    return

                env.cr.commit()

                if action_after in ('validate', 'confirm'):
                    self.sudo(user_id)._perform_job_schedule_validation(action_after)

                line.sudo().write({'busy': False})  # Whatever the outcome of the validation - reset line busy state
                env.cr.commit()
                env.cr.close()
            except Exception as e:
                self.env.cr.rollback()
                env.cr.rollback()
                env.cr.close()
                self.sudo().write({'busy': False})
                self.env.cr.commit()
                raise e

    @api.multi
    def _perform_job_schedule_validation(self, action_after):
        if not action_after:
            return
        user = self.env.user

        with Environment.manage():
            # Create a new cursor for validation
            new_cr = self.pool.cursor()
            context = self.env.context.copy()
            validation_env = api.Environment(new_cr, user.id, context)
            lines_to_validate = validation_env['work.schedule.line'].browse(self.ids)

            try:
                # Try to perform the validation
                if action_after == 'validate':
                    lines_to_validate.with_context(ignore_busy=True).finalise_validation()
                elif action_after == 'confirm':
                    lines_to_validate.with_context(ignore_busy=True).finalise_confirmation()
            except Exception as e:
                validation_env.cr.rollback()
                if not self._context.get('method_running_as_job'):
                    raise e

                # Ignore access errors when confirming/validating as a job. When line constraints are checked and the
                # user tries to validate again - the code should fail
                access_error = any(isinstance(e, instance_type) for instance_type in (
                    exceptions.AccessDenied, exceptions.AccessError
                ))
                if not access_error:
                    try:
                        ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
                        exception_message = e.message or repr(e) or str(e.args)
                        subject = '[%s] Job to confirm work schedule after checking constraints has failed' % self._cr.dbname
                        body = """Error: {}""".format(exception_message)
                        vals = {
                            'ticket_dbname': self.env.cr.dbname,
                            'ticket_model_name': self._name,
                            'ticket_record_id': False,
                            'name': subject,
                            'ticket_user_login': user.login,
                            'ticket_user_name': user.name,
                            'description': body,
                            'ticket_type': 'bug',
                            'user_posted': user.name
                        }
                        res = ticket_obj.create_ticket(**vals)
                        if not res:
                            raise exceptions.UserError('The distant method did not create the ticket.')
                    except Exception as e:
                        message = 'Failed to create job failure ticket for work schedule validation.\nException: %s' % (
                            str(e.args))
                        self.env['robo.bug'].sudo().create({
                            'user_id': user.id,
                            'error_message': message,
                        })
            finally:
                validation_env.cr.commit()
                validation_env.cr.close()

    @api.multi
    def get_failed_constraint_string(self):
        err_string = self.get_related_missing_employees_warning()

        failed_lines = self.filtered(lambda l: not l.busy and l.constraint_check_data not in [None, False, '', 'VALID'])
        if failed_lines:
            err_string += '\n\n'.join(failed_lines.mapped('constraint_check_data'))

        busy_lines = self.filtered(lambda l: l.busy)
        if busy_lines:
            err_string += _("Constraints for some lines are still being checked. Please wait and check the failed "
                            "constraints later for the following employees: {}\n").format(
                '\n'.join(busy_lines.mapped('employee_id.name'))
            )
        return err_string

    @api.multi
    def show_failed_line_constraints(self, raise_on_success=False):
        err_string = self.get_failed_constraint_string()
        if err_string != '':
            raise exceptions.UserError(err_string)
        elif raise_on_success:
            raise exceptions.UserError(_('Schedule meets the requirements'))

    @api.model
    def get_constraint_status(self, busy, constraint_check_data):
        if busy:
            return 'busy'
        elif constraint_check_data == 'VALID':
            return 'valid'
        elif constraint_check_data in [None, False, '']:
            return 'not_checked'
        else:
            return 'failed'
