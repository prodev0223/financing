# -*- coding: utf-8 -*-

from odoo import models, fields


class HrJob(models.Model):
    _inherit = 'hr.job'

    use_royalty = fields.Boolean(
        string='Taikyti honorarus', groups='robo_basic.group_robo_premium_accountant'
    )


HrJob()
