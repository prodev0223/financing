# -*- encoding: utf-8 -*-
from odoo import models, fields


class AccountAccountTag(models.Model):
    _inherit = 'account.account.tag'

    code = fields.Char(string='Code')
    base = fields.Boolean(string='Base', default=False)
