# -*- coding: utf-8 -*-
from odoo import fields, models, _


class IrModelFields(models.Model):

    _inherit = 'ir.model.fields'

    sequence = fields.Integer(string="Sequence")


IrModelFields()