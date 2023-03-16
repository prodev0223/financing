# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeBonus(models.Model):
    _inherit = 'hr.employee.bonus'

    exclude_bonus_from_du_aspi = fields.Boolean(string='Do not include in DU-ASPI', )
