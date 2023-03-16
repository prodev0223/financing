# -*- coding: utf-8 -*-

from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    recruitment_date = fields.Date(string='Įdarbinimo data')
    contract_wage = fields.Float(string='Sutartinis darbo užmokestis', digits=(16, 2))
    employee_manager = fields.Char(string='Vadovas')
    job_name = fields.Char(string='Pareigos (anglų k.)')
    payroll_schema = fields.Char(string='DU schema')
    show_extra_information_tab = fields.Boolean(compute='_compute_show_extra_information_tab')

    def _compute_show_extra_information_tab(self):
        """
        Check if per-user additional personal information tab should be displayed on employee card
        """
        for rec in self:
            if (rec.sudo().user_id and rec.sudo().user_id.id == self.env.user.id) or self.env.user.is_manager() or \
                    self.env.user.is_hr_manager():
                rec.show_extra_information_tab = True


HrEmployee()
