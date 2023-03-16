# -*- coding: utf-8 -*-
from odoo import fields, models


class IrModelFields(models.Model):

    _inherit = 'ir.model.fields'

    dynamic_report_front_filter = fields.Boolean(string='Is dynamic report filter',
                                                 help='Is the field a filter for a dynamic report')
