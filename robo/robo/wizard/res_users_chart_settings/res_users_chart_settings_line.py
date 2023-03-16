# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools
from dateutil.relativedelta import relativedelta
from datetime import datetime


class ResUsersChartSettingsLine(models.TransientModel):

    """
    Model that is used in a wizard to set budget lines (forecast.budget.line)
    """

    _name = 'res.users.chart.settings.line'

    @api.model
    def _expected_date(self):
        return (datetime.now() + relativedelta(months=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    expected_date = fields.Date(string='Prognozuojama data', default=_expected_date)
    expected_amount = fields.Float(string='Prognozuojama suma (kompanijos valiuta)')
    original_line_id = fields.Many2one('forecast.budget.line')
    wizard_id = fields.Many2one('res.users.chart.settings')


ResUsersChartSettingsLine()
