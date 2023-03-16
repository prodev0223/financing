# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountAssetDepartment(models.Model):

    _name = 'account.asset.department'

    name = fields.Char(string='Name', required=True)


AccountAssetDepartment()