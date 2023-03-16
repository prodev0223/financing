# -*- encoding: utf-8 -*-

from odoo import models, fields, _, api, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class AnalyticAccountRefreshWizard(models.TransientModel):

    _name = 'analytic.account.refresh.wizard'

    def default_date_from(self):
        return datetime.now() + relativedelta(month=1, day=1)

    def default_date_to(self):
        return datetime.now()

    date_from = fields.Date(string='Data nuo', required=True, default=default_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=default_date_to)

    @api.multi
    def refresh_analytic_accounts(self):
        self.ensure_one()

        if self.date_from > self.date_to:
            raise exceptions.UserError(_('Datų intervalo pradžia turi būti prieš pabaigą'))

        if not self.env.user.has_group('doarchitects.group_analytic_account_refresh'):
            return

        self.env['account.analytic.line'].sudo().cron_refresh_analytic_accounts_period(self.date_from, self.date_to)


AnalyticAccountRefreshWizard()
