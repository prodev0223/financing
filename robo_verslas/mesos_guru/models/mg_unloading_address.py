# -*- coding: utf-8 -*-

from odoo import models, fields


class MGUnloadingAddress(models.Model):
    _name = 'mg.unloading.address'

    name = fields.Char(string='Iškrovimo vieta', required=True)


MGUnloadingAddress()
