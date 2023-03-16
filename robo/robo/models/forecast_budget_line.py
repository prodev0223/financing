# -*- coding: utf-8 -*-
from odoo import fields, models


class ForecastBudgetLine(models.Model):
    """
    Model that holds forecast budget line objects for specific user.
    User can customise their expenses/income, data is shown in forecast chart
    """
    _name = 'forecast.budget.line'

    expected_date = fields.Date(string='Prognozuojama data')
    expected_amount = fields.Float(string='Prognozuojama suma (kompanijos valiuta)')
    user_id = fields.Many2one('res.users', string='Naudotojas')
