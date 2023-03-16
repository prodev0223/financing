# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class AnalyticAccountBudgetLine(models.Model):
    _name = 'analytic.account.budget.line'

    def get_default_account(self):
        return self._context.get('parent_id', False)

    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki', required=True)
    account_analytic_id = fields.Many2one('account.analytic.account',
                                          string='Analitinė sąskaita', required=True,
                                          readonly=True, default=get_default_account)
    expense_budget = fields.Float(string='Planuojamos išlaidos')
    income_budget = fields.Float(string='Planuojamos pajamos')

    @api.multi
    @api.constrains('date_from', 'date_to')
    def date_constrains(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki'))
