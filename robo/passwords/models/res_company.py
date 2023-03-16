# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    password_expiration = fields.Integer('Days', default=60, help='Password will expire after')
    password_length = fields.Integer('Characters', default=12, help='Minimum number of characters')
    password_lower = fields.Boolean('Lowercase', default=True, help='Require lowercase letters')
    password_upper = fields.Boolean('Uppercase', default=True, help='Require uppercase letters')
    password_numeric = fields.Boolean('Numeric', default=True, help='Require numeric digits')
    password_special = fields.Boolean('Special', default=False, help='Require special characters')

ResCompany()
