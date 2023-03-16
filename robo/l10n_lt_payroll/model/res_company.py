# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, models, fields, tools


class ResCompany(models.Model):
    _inherit = 'res.company'

    holiday_accumulation_usage_policy = fields.Boolean(
        string='Use holiday accumulation and usage records when calculating holiday payments'
    )
    holiday_accumulation_usage_start_date = fields.Date(
        string='Date from which the company uses holiday accumulation and usage records',
        compute='_compute_holiday_accumulation_usage_start_date',
        inverse='_set_holiday_accumulation_usage_start_date'
    )
    holiday_accumulation_usage_is_enabled = fields.Boolean(compute='_compute_holiday_accumulation_usage_is_enabled')

    @api.multi
    def _compute_holiday_accumulation_usage_start_date(self):
        sys_param = self.env['ir.config_parameter'].sudo().get_param('holiday_accumulation_usage_start_date')
        # Holiday accumulation was implemented sometime in June 2021. No companies should be using this before July 2021
        self.holiday_accumulation_usage_start_date = sys_param or '2021-07-01'

    @api.multi
    def _set_holiday_accumulation_usage_start_date(self):
        self.ensure_one()
        if self.holiday_accumulation_usage_start_date:
            self.env['ir.config_parameter'].sudo().set_param(
                'holiday_accumulation_usage_start_date', self.holiday_accumulation_usage_start_date
            )

    @api.multi
    @api.depends('holiday_accumulation_usage_policy', 'holiday_accumulation_usage_start_date')
    def _compute_holiday_accumulation_usage_is_enabled(self):
        date = self.env.context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            company_holiday_accumulation_usage_start_date = rec.holiday_accumulation_usage_start_date
            rec.holiday_accumulation_usage_is_enabled = rec.holiday_accumulation_usage_policy and \
                                                        company_holiday_accumulation_usage_start_date <= date

    @api.multi
    def _get_payroll_account_ids(self):
        self.ensure_one()
        # TODO When l10n_lt_payroll depends on l10n_lt which should depend on robo - implement empty base method in
        #  robo and call super first
        # The following super call should get payroll expense account ids
        # res = super(ResCompany, self)._get_payroll_account_ids()
        res = self._get_payroll_expense_account_ids()
        accounts = self.env['account.account'].search([
            ('code', 'in', ['24450', '24451', '4483'])
        ])
        accounts |= self.saskaita_komandiruotes_credit

        res += accounts.ids
        return res

    @api.multi
    def _get_payroll_expense_account_ids(self):
        # TODO When l10n_lt_payroll depends on l10n_lt which should depend on robo - implement empty base method in
        #  robo and call super first
        # res = super(ResCompany, self)._get_payroll_expense_account_ids()
        res = []
        accounts = self.env['account.account']
        accounts |= self.saskaita_debetas
        accounts |= self.env['account.account'].search([('code', 'in', ['63045'])], limit=1)
        accounts |= self.saskaita_komandiruotes
        accounts |= self.darbdavio_sodra_debit

        department_ids = self.env['hr.department'].sudo().search([])
        accounts |= department_ids.mapped('saskaita_debetas')
        accounts |= department_ids.mapped('darbdavio_sodra_debit')

        res += accounts.ids
        return res
