# -*- coding: utf-8 -*-

from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    next_medical_knowledge_certificate_date = fields.Date(
        string="Sveikatos žinių atestavimo pažymėjimo sekanti patikros data",
        required=False, groups='robo_basic.group_robo_free_manager,'
        'robo_basic.group_robo_premium_manager,'
        'robo_basic.group_robo_hr_manager')


HrEmployee()
