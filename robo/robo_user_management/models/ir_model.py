# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import AccessError


class IrModel(models.Model):
    _inherit = 'ir.model'

    allow_access_changes = fields.Boolean(string='Leisti keisti prieigos teises')


IrModel()
