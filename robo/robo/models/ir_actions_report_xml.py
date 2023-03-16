# -*- coding: utf-8 -*-


from odoo import fields, models


class IrActionsReportXml(models.Model):
    _inherit = 'ir.actions.report.xml'

    robo_front = fields.Boolean(string='Ar rodyti veiksmą vartotojui?', default=False)
