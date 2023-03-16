# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticGroup(models.Model):
    _name = 'account.analytic.group'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)


AccountAnalyticGroup()
