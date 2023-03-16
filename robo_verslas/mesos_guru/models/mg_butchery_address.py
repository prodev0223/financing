# -*- coding: utf-8 -*-

from odoo import models, fields


class MGButcheryAddress(models.Model):
    _name = 'mg.butchery.address'

    name = fields.Char(string='Skerdyklos vieta', required=True)


MGButcheryAddress()
