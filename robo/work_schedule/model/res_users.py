# -*- coding: utf-8 -*-

from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.multi
    def is_schedule_user(self):
        self.ensure_one()
        return self.has_group('work_schedule.group_schedule_user')

    @api.multi
    def is_schedule_manager(self):
        self.ensure_one()
        return self.has_group('work_schedule.group_schedule_manager')

    @api.multi
    def is_schedule_super(self):
        self.ensure_one()
        return self.has_group('work_schedule.group_schedule_super')

    @api.multi
    def schedule_fill_department_ids(self):
        self.ensure_one()
        return self.mapped('employee_ids.fill_department_ids')

    @api.multi
    def get_departments_user_can_edit(self):
        self.ensure_one()
        departments_user_can_edit = self.env['hr.department']
        if self.is_schedule_super():
            departments_user_can_edit |= self.env['hr.department'].with_context(active_test=False).search([])
        else:
            user_employees = self.mapped('employee_ids')
            if self.is_schedule_manager():
                departments_user_can_edit |= user_employees.mapped('department_id')
            departments_user_can_edit |= user_employees.mapped('fill_department_ids')
        return departments_user_can_edit

    @api.multi
    def can_modify_schedule_departments(self, department_ids, must_be_all=True):
        if not department_ids:
            return False
        fill_department_ids = self.mapped('employee_ids.fill_department_ids.id')
        if must_be_all:
            return all(department_id in fill_department_ids for department_id in department_ids)
        else:
            return any(department_id in fill_department_ids for department_id in department_ids)

    @api.multi
    def can_validate_schedule_departments(self, department_ids, must_be_all=True):
        if not department_ids:
            return False
        validate_department_ids = self.mapped('employee_ids.validate_department_ids.id')
        if must_be_all:
            return all(department_id in validate_department_ids for department_id in department_ids)
        else:
            return any(department_id in validate_department_ids for department_id in department_ids)

    @api.multi
    def can_confirm_schedule_departments(self, department_ids, must_be_all=True):
        if not department_ids:
            return False
        confirm_department_ids = self.mapped('employee_ids.confirm_department_ids.id')
        if must_be_all:
            return all(department_id in confirm_department_ids for department_id in department_ids)
        else:
            return any(department_id in confirm_department_ids for department_id in department_ids)

    @api.multi
    def get_work_schedule_access_level(self):
        self.ensure_one()
        if self.has_group('robo_basic.group_robo_premium_chief_accountant'):
            return 5
        elif self.is_accountant():
            return 4
        elif self.is_schedule_super():
            return 3
        elif self.is_schedule_manager():
            return 2
        else:
            return 1
