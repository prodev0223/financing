# -*- encoding: utf-8 -*-
from odoo import fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('multiple_form_tree', 'Multiple From Tree')])


IrUiView()
