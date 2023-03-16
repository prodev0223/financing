# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _


class StateDeclaredEmergency(models.Model):
    _name = 'state.declared.emergency'

    name = fields.Char(string='Name', required=True)
    date_start = fields.Datetime(string='Start date')
    date_end = fields.Datetime(string='End date')
    reference_text = fields.Text(string='Text that refers to the document', required=True)
