# -*- coding: utf-8 -*-


from odoo import fields, models


class IrActionsClient(models.Model):
    _inherit = 'ir.actions.client'

    robo_front = fields.Boolean(string='Ar rodyti veiksmą vartotojui?', default=False)
