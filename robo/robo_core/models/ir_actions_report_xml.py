# -*- coding: utf-8 -*-
from odoo import fields, models


class IrActionsReportXML(models.Model):
    _inherit = 'ir.actions.report.xml'

    print_report_name = fields.Char(translate=True)
