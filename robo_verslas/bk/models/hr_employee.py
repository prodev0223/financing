# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    analytic_type = fields.Selection(default='payroll_schedule')
