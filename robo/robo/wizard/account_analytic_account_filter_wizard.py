# -*- coding: utf-8 -*-


import ast
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools


class AccountAnalyticAccountFilterWizard(models.TransientModel):
    _name = 'account.analytic.account.filter.wizard'

    def default_date_from(self):
        return (datetime.utcnow() + relativedelta(month=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    date_from = fields.Date(string='Data nuo', required=True, default=default_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=default_date_to)

    @api.multi
    def return_action(self):
        self.ensure_one()
        action = self.env.ref('robo_analytic.action_analytic_account_form').read()[0]
        ctx = {
            'from_date': self.date_from,
            'to_date': self.date_to,
        }
        # Only recompute debit/credit/balance when opening the report
        self.env['account.analytic.account'].search([]).sudo().with_context(ctx)._compute_debit_credit_balance()
        context = ast.literal_eval(action['context'])
        context.update(ctx)
        action['context'] = context
        return action
