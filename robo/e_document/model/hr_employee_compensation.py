# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployeeCompensation(models.Model):
    _inherit = 'hr.employee.compensation'

    related_document = fields.Many2one('e.document', string='Susijęs dokumentas',
                                       states={'confirm': [('readonly', True)]})


HrEmployeeCompensation()
