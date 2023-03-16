# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResUsersChartSettings(models.TransientModel):

    """
    Module that is used to set chart settings for specific user.
    Used only on cash-flow forecast chart at the moment
    """

    _name = 'res.users.chart.settings'

    average_expenses_forecast = fields.Boolean(
        groups='robo_basic.group_robo_premium_manager',
        string='Traukti vidutines 3mėn. išlaidas (Sąskaitos faktūros)'
    )

    average_income_forecast = fields.Boolean(
        groups='robo_basic.group_robo_premium_manager',
        string='Traukti vidutines 3mėn. pajamas (Sąskaitos faktūros)'
    )

    average_du_forecast = fields.Boolean(
        groups='robo_basic.group_robo_premium_manager',
        string='Traukti vidutines DU sąnaudas'
    )

    include_income = fields.Boolean(
        groups='robo_basic.group_robo_premium_manager',
        string='Traukti gautinas sumas'
    )

    include_expenses = fields.Boolean(
        groups='robo_basic.group_robo_premium_manager',
        string='Traukti mokėtinas sumas'
    )

    settings_line_ids = fields.One2many('res.users.chart.settings.line', 'wizard_id')

    @api.model
    def default_get(self, field_list):
        if not self.env.user.is_manager():
            return {}
        user_id = self.env.user
        line_ids = []
        for line in user_id.forecast_budget_line_ids:
            vals = {
                'expected_date': line.expected_date,
                'expected_amount': line.expected_amount,
                'original_line_id': line.id,
            }
            line_ids.append((0, 0, vals))

        res = {
            'average_expenses_forecast': user_id.average_expenses_forecast,
            'average_income_forecast': user_id.average_income_forecast,
            'average_du_forecast': user_id.average_du_forecast,
            'include_income': user_id.include_income,
            'include_expenses': user_id.include_expenses,
            'settings_line_ids': line_ids
        }
        return res

    @api.multi
    def save_chart_settings(self):
        """
        Write forecast chart settings and budget line changes to non-transient models
        :return: None
        """
        self.ensure_one()
        if not self.env.user.is_manager():
            return
        user_id = self.env.user
        vals = {
            'average_expenses_forecast': self.average_expenses_forecast,
            'average_income_forecast': self.average_income_forecast,
            'average_du_forecast': self.average_du_forecast,
            'include_income': self.include_income,
            'include_expenses': self.include_expenses,
        }
        user_id.write(vals)
        original_lines = user_id.forecast_budget_line_ids
        deleted_lines = original_lines.filtered(
            lambda x: x.id not in self.settings_line_ids.mapped('original_line_id.id'))

        changed_lines = self.settings_line_ids.filtered(lambda x: x.original_line_id)

        new_lines = self.settings_line_ids.filtered(lambda x: not x.original_line_id)

        # Change lines
        for line in changed_lines:
            line.original_line_id.write(
                {'expected_date': line.expected_date, 'expected_amount': line.expected_amount})

        # Delete lines
        deleted_lines.unlink()

        # Add lines
        for line in new_lines:
            vals = {
                'expected_date': line.expected_date,
                'expected_amount': line.expected_amount,
                'user_id': user_id.id
            }
            self.env['forecast.budget.line'].create(vals)


ResUsersChartSettings()
