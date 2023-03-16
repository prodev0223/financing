# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    readonly_department_id = fields.Boolean(compute='_compute_readonly_department_id')

    @api.multi
    def _compute_readonly_department_id(self):
        """
        Compute //
        Always False if record is not yet created.
        After record is created, compute is called,
        field is editable only for accountants.
        :return: None
        """
        if not self.env.user.is_accountant():
            for rec in self:
                rec.readonly_department_id = True


HrEmployee()
