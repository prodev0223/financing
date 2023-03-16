# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeCompensationTimeLine(models.Model):
    _name = 'hr.employee.compensation.time.line'
    _inherit = ['robo.time.line']

    compensation_id = fields.Many2one('hr.employee.compensation', required=True, ondelete='cascade')


HrEmployeeCompensationTimeLine()
