# -*- coding: utf-8 -*-
from odoo import models, api, tools, _
from datetime import datetime


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    @api.onchange('date_planned_start')
    def _onchange_date_planned_start_acc_date(self):
        """Set accounting date to date planned start or date-now"""
        if self.force_accounting_date:
            date = self.date_planned_start or datetime.now().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            self.accounting_date = date
