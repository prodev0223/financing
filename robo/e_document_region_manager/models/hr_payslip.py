# -*- coding: utf-8 -*-
from odoo import models, api


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    @api.multi
    def print_payslip_note(self):
        self.ensure_one()
        if self.env.user.is_region_manager_at_date(self.sudo().employee_id.department_id.id):
            self = self.sudo()
        return super(HrPayslip, self).print_payslip_note()

    @api.multi
    def payslip_data_is_accessible(self):
        """
        Check if payslip data is accessible for current user
        l10n_lt_payroll: Fully overridden
        :return: Indicator if payslip data is accessible for user
        """
        self.ensure_one()
        user = self.env.user
        is_accessible = user.is_hr_manager() or user.is_manager() or \
                        user.is_region_manager_at_date(self.employee_id.department_id.id) or \
                        self.employee_id.user_id.id == self._uid
        return is_accessible
