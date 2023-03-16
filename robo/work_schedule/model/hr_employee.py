# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, fields, _
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    robo_work_schedule_group = fields.Selection([('employee', _('Darbuotojas')),
                                                 ('department_manager', _('Skyriaus administratorius')),
                                                 ('super_user', _('Vadovas'))],
                                                default='employee',
                                                string='Darbo grafiko teisių grupė',
                                                groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager',
                                                inverse='_set_robo_work_schedule_access',
                                                )

    fill_department_ids = fields.Many2many(
        'hr.department',
        string='Pildomi grafiko skyriai',
        help='Šis darbuotojas gaus teisę pildyti šių skyrių grafikus',
        relation='rel_hr_employee_fill_department_ids',
        groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager',
        inverse='clear_ir_rule_cache',
        sequence=100,
    )
    validate_department_ids = fields.Many2many(
        'hr.department',
        string='Tvirtinami grafiko skyriai',
        help='Šis darbuotojas gaus teisę patvirtinti šių skyrių grafikus',
        relation='rel_hr_employee_validate_department_ids',
        groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager',
        inverse='clear_ir_rule_cache',
        sequence=100,
    )
    confirm_department_ids = fields.Many2many(
        'hr.department',
        string='Pateikiami grafiko skyriai',
        help='Šis darbuotojas gaus teisę pateikti šių skyrių grafikus',
        relation='rel_hr_employee_confirm_department_ids',
        groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager',
        inverse='clear_ir_rule_cache',
        sequence=100,
    )
    can_fill_own_schedule = fields.Boolean(string='Gali pildyti savo grafiką',
                                               groups='robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager',
                                           )
    bypass_day_constraints = fields.Boolean(string='Grafike neriboti valandų skaičiaus per dieną', default=False,
                                            groups='robo_basic.group_robo_premium_accountant',
                                            )

    @api.multi
    def update_mail_channel_subscription_and_clear_ir_rule_cache(self):
        fill_schedule_reminder_mail_channel = self.env.ref('work_schedule.fill_schedule_reminder_mail_channel',
                                                           raise_if_not_found=False)
        for employee in self:
            if not fill_schedule_reminder_mail_channel:
                return
            partner = employee.address_home_id
            if not partner:
                continue
            if employee.sudo().confirm_department_ids or employee.sudo().validate_department_ids:
                fill_schedule_reminder_mail_channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})
            else:
                user = employee.user_id
                if user and not user.has_group('work_schedule.group_schedule_manager'):
                    fill_schedule_reminder_mail_channel.sudo().write({'channel_partner_ids': [(3, partner.id)]})

        self.clear_ir_rule_cache()

    @api.model
    def clear_ir_rule_cache(self):
        self.env['ir.rule'].clear_caches()

    @api.one
    def _set_robo_access(self):
        res = super(HrEmployee, self)._set_robo_access()
        self._set_robo_work_schedule_access()
        return res

    @api.one
    def _set_robo_work_schedule_access(self):
        if self.user_id:
            schedule_group = self.sudo().robo_work_schedule_group
            if self.sudo().user_id.is_schedule_user():
                self.sudo().user_id.groups_id = [
                    (3, self.sudo().env.ref('work_schedule.group_schedule_user').id,)]
            if self.sudo().user_id.is_schedule_manager():
                self.sudo().user_id.groups_id = [
                    (3, self.sudo().env.ref('work_schedule.group_schedule_manager').id,)]
            if self.sudo().user_id.is_schedule_super():
                self.sudo().user_id.groups_id = [
                    (3, self.sudo().env.ref('work_schedule.group_schedule_super').id,)]

            if schedule_group == 'department_manager':
                self.sudo().user_id.groups_id = [
                    (4, self.sudo().env.ref('work_schedule.group_schedule_manager').id,)]
            elif schedule_group == 'super_user':
                self.sudo().user_id.groups_id = [
                    (4, self.sudo().env.ref('work_schedule.group_schedule_super').id,)]
            else:
                self.sudo().user_id.groups_id = [
                    (4, self.sudo().env.ref('work_schedule.group_schedule_user').id,)]

            company = self.env.user.company_id
            is_extended = company.extended_schedule if company else False
            menu_group = self.env.ref('work_schedule.group_schedule_menu_visible', raise_if_not_found=False)
            base_user_group = self.env.ref('work_schedule.group_schedule_user', raise_if_not_found=False)
            if not menu_group or not base_user_group:
                return
            if is_extended:
                self.user_id.write({'groups_id': [(4, menu_group.id,)]})
            else:
                self.user_id.write({'groups_id': [(3, menu_group.id,)]})

    @api.multi
    @api.depends('name', 'type')
    def _show_remaining_leaves(self):
        super(HrEmployee, self)._show_remaining_leaves()
        user = self.env.user
        if user.is_schedule_manager() or user.is_schedule_super():
            for rec in self:
                if rec.sudo().type != 'mb_narys':
                    rec.show_remaining_leaves = True

    @api.multi
    def _remaining_leaves(self):
        super(HrEmployee, self)._remaining_leaves()
        date = self._context.get('date', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        user = self.env.user
        for rec in self:
            if user.is_schedule_manager() or user.is_schedule_super():
                rec.remaining_leaves = rec._compute_employee_remaining_leaves(date)

    @api.multi
    def get_managing_departments(self):
        managing_departments = super(HrEmployee, self).get_managing_departments()
        employee_users_managing_work_schedule = self.mapped('user_id').filtered(
            lambda user: user.has_group('work_schedule.group_schedule_manager')
        )
        related_employees = employee_users_managing_work_schedule.mapped('employee_ids').filtered(
            lambda employee: employee.id in self.ids
        )
        managing_departments |= related_employees.mapped('department_id')
        return managing_departments

    @api.model
    def should_see_all_other_employees(self):
        return super(HrEmployee, self).should_see_all_other_employees() or \
               self.env.user.has_group('work_schedule.group_schedule_super')

    @api.multi
    def get_worked_time(self, date_from, date_to):
        """
        Gets worked time for specific employees for specified date range. Overrides parent method and gets preliminary
        time from schedule.
        @param date_from: (str) Date from to get the work time for
        @param date_to: (str) Date to to get the work time for
        """
        worked_time_codes = PAYROLL_CODES['WORKED'] + PAYROLL_CODES['OUT_OF_OFFICE'] + \
                            PAYROLL_CODES['UNPAID_OUT_OF_OFFICE'] + PAYROLL_CODES['DOWNTIME']

        data = super(HrEmployee, self).get_worked_time(date_from, date_to)

        # Find work schedule days for preliminary employees
        employee_ids = [employee_id for employee_id in data.keys() if data[employee_id].get('is_preliminary')]

        # Compute dates
        date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        last_of_current_month = datetime.now() + relativedelta(day=31)

        # Figure out which schedule to take data from
        if last_of_current_month < date_dt:
            schedule_to_use = self.env.ref('work_schedule.planned_company_schedule')
        else:
            schedule_to_use = self.env.ref('work_schedule.factual_company_schedule')

        # Find work schedule days
        work_schedule_days = self.env['work.schedule.day'].search([
            ('employee_id', 'in', employee_ids),
            ('date', '<=', date_to),
            ('date', '>=', date_from),
            ('work_schedule_id', '=', schedule_to_use.id)
        ])

        # Update data for employees with preliminary times
        for employee in work_schedule_days.mapped('employee_id'):
            employee_days = work_schedule_days.filtered(lambda d: d.employee_id == employee).filtered(
                lambda d: not d.holiday_ids and not d.schedule_holiday_id
            )
            employee_lines = employee_days.mapped('line_ids').filtered(lambda l: l.code in worked_time_codes)
            data[employee.id] = {
                'worked_time': sum(employee_lines.mapped('worked_time_total')),
                'is_preliminary': True  # Always preliminary since we're getting data from schedule
            }
        return data


HrEmployee()
