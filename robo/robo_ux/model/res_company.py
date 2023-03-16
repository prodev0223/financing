# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    robo_ux_settings_id = fields.Many2one('robo.ux.settings')


ResCompany()
