# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    pension_fund_id = fields.Many2one('res.pension.fund', string='Pension fund')
