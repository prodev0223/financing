# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta
from six import iteritems

from odoo import _, models, api, tools, fields


class AccountCashFlowReport(models.TransientModel):
    _name = 'account.cashflow.report'
    _inherit = ['account.cashflow.report', 'dynamic.report']

    _dr_base_name = _('Account cash flow report')
    _report_tag = 'dynamic.cashflow'

    date_range = fields.Selection(default='')
    hierarchy_level = fields.Selection(string='Detail level', default='7', dynamic_report_front_filter=True)
    target_move = fields.Selection(dynamic_report_front_filter=True)

    @api.multi
    def check_report(self):
        self.update_force_lang()
        return super(AccountCashFlowReport, self).check_report()

    @api.multi
    def update_force_lang(self):
        for rec in self:
            rec.write({'force_lang': rec.report_language})

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        # Prepare data
        base_data = self.with_context(force_html=True).check_report()
        form = base_data.get('data', {}).get('form')
        if not form:
            return []

        accounts = self.env['account.account'].with_context(show_views=True).search([])
        used_context = form.get('used_context', {})
        used_context['force_return_data'] = True
        ReportObj = self.env['report.sl_general_report.report_cashflowstatement_sl']
        accounts_res = ReportObj.with_context(used_context)._get_account_move_entry(accounts, form['hierarchy_level'])

        company_currency = self.env.user.company_id.currency_id

        account_move_line_action = self.env.ref('l10n_lt.account_move_line_robo_front_action', False)

        # Form res
        res = []
        for i, view_account in enumerate(accounts_res):
            view_account_id = 'view_account_{}'.format(i)
            view_accounts = view_account.get('accounts')
            view_account_data = {'value': view_account_id, 'name': view_account.get('name')}
            if not view_accounts:
                res.append({'view_account': view_account_data})  # Empty line to show on dynamic report view
            for account in view_accounts:
                account_values = {key: {'value': value} for key, value in iteritems(account)}
                account_values['view_account'] = view_account_data
                account_values['cashflow_balance']['currency_id'] = company_currency.id
                account_values['__record_data__'] = {
                    'record_model': 'account.move.line',
                    'record_ids': account.get('move_line_ids', []),
                    'action_id': account_move_line_action.id if account_move_line_action else None
                }
                res.append(account_values)
        return res

    @api.multi
    def get_pdf_header(self):
        self.ensure_one()
        return self.env['ir.qweb'].render('robo_dynamic_reports.CashFlowPDFHeader')

    @api.multi
    def get_pdf_footer(self):
        self.ensure_one()
        start_date = (datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT) -
                      relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        ReportObj = self.env['report.sl_general_report.report_cashflowstatement_sl']
        beginning_balance = ReportObj.calculate_cash_bank_balance('1900-01-01', start_date)
        period_balance = ReportObj.calculate_cash_bank_balance(self.date_from, self.date_to)
        return self.env['ir.qweb'].render('robo_dynamic_reports.CashFlowPDFFooter', {
            'beginning_balance': beginning_balance,
            'period_balance': period_balance,
            'end_balance': beginning_balance + period_balance,
            'currency': self.env.user.company_id.currency_id
        })
