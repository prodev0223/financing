# -*- encoding: utf-8 -*-
from odoo import models, fields


class ActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(selection_add=[('multiple_form_tree', 'Multiple From Tree')])


ActWindowView()
