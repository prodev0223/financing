# -*- coding: utf-8 -*-

from odoo import fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('workschedule', 'Payroll Schedule')])


IrUiView()