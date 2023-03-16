# -*- coding: utf-8 -*-

import time
from odoo import api, models, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.sl_general_report.report_trialbalance_sl'

    def _get_accounts(self, accounts, display_account):
        """ compute the balance, debit and credit for the provided accounts
            :Arguments:
                `accounts`: list of accounts record,
                `display_account`: it's used to display either all accounts or those accounts which balance is > 0
            :Returns a list of dictionary of Accounts with following key and value
                `name`: Account name,
                `code`: Account code,
                `credit`: total amount of credit,
                `debit`: total amount of debit,
                `balance`: total amount of balance,
        """
        account_result_history = {}
        if self._context.get('date_from'):
            date_to = (datetime.strptime(self._context.get('date_from'), tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            tables, where_clause, where_params = self.with_context(date_from=False, date_to=date_to).env['account.move.line']._query_get()
            tables = tables.replace('"', '')
            if not tables:
                tables = 'account_move_line'
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())
            filters = " AND ".join(wheres)
            # compute the balance, debit and credit for the provided accounts
            request = (
            "SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, (SUM(debit) - SUM(credit)) AS balance" +
            " FROM " + tables + " WHERE account_id IN %s " + filters + " GROUP BY account_id")
            params = (tuple(accounts.ids),) + tuple(where_params)
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                account_result_history[row.pop('id')] = row

        account_result = {}
        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = self.env['account.move.line']._query_get()
        tables = tables.replace('"', '')
        if not tables:
            tables = 'account_move_line'
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        # compute the balance, debit and credit for the provided accounts
        request = ("SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, (SUM(debit) - SUM(credit)) AS balance" +
                   " FROM " + tables + " WHERE account_id IN %s " + filters + " GROUP BY account_id")
        params = (tuple(accounts.ids),) + tuple(where_params)
        self.env.cr.execute(request, params)
        for row in self.env.cr.dictfetchall():
            account_result[row.pop('id')] = row

        account_res = []
        account_res_dict = {}
        for account in accounts:
            res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
            currency = account.currency_id and account.currency_id or account.company_id.currency_id
            res['code'] = account.code
            res['name'] = account.name
            if account.id in account_result.keys():
                res['debit'] = account_result[account.id].get('debit')
                res['credit'] = account_result[account.id].get('credit')
                res['balance'] = account_result[account.id].get('balance')
            if account.id in account_result_history:
                res['start_balance'] = account_result_history[account.id].get('balance')
                res['balance'] += res['start_balance']
            else:
                res['start_balance'] = 0.0

            not_zero_balance_or_start_balance = (not currency.is_zero(res['balance']) or
                                                 not currency.is_zero(res['start_balance']))
            not_zero_credit_or_debit = (not currency.is_zero(res['credit']) or not currency.is_zero(res['debit']))

            if display_account == 'all':
                account_res.append(res)
                account_res_dict[account.id] = res
            elif (display_account == 'not_zero' and not_zero_balance_or_start_balance) or \
                    (display_account == 'movement' and not_zero_credit_or_debit):
                account_res.append(res)
                account_res_dict[account.id] = res
            elif display_account == 'movement_or_not_zero' and (not_zero_balance_or_start_balance or
                                                                not_zero_credit_or_debit):
                account_res.append(res)
                account_res_dict[account.id] = res

        acc_views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True)],
                                                       limit=1, order='hierarchy_level DESC')
        if acc_views:
            account_hierarchy = acc_views[0].hierarchy_level
        else:
            account_hierarchy = 11
        for i in range(account_hierarchy, 0, -1):
            account_res_dict = self.calculate_view_balance(account_res_dict, i)
        return account_res

    def calculate_view_balance(self, account_list, hierarchy_level):
        views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True),
                                                    ('hierarchy_level', '=', hierarchy_level)])

        for view in views:
            children = self.env['account.account'].with_context(show_views=True).search([('parent_id', '=', view.id)])
            if view.id in account_list.keys():
                debit = account_list[view.id]['debit']
                credit = account_list[view.id]['credit']
                balance = account_list[view.id]['balance']
            else:
                debit = 0
                credit = 0
                balance = 0
            for child in children:
                if child.id in account_list.keys():
                    debit += account_list[child.id]['debit']
                    credit += account_list[child.id]['credit']
                    balance += account_list[child.id]['balance']
            if view.id in account_list.keys():
                account_list[view.id]['debit'] = debit
                account_list[view.id]['credit'] = credit
                account_list[view.id]['balance'] = balance
        return account_list

    @api.multi
    def render_html(self, doc_ids, data=None):
        model = self.env.context.get('active_model') or 'account.balance.report'
        docs = self.env[model].browse(self.env.context.get('active_id'))
        display_account = data['form'].get('display_account')
        lang = self.env.user.lang or self._context.get('lang') or self.env.user.company_id.partner_id.lang or 'lt_LT'
        self = self.with_context(show_views=False, lang=lang)
        accounts = self.env['account.account'].search([])
        account_res = self.with_context(data['form'].get('used_context'))._get_accounts(accounts, display_account)

        docargs = {
            'doc_ids': doc_ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': account_res,
        }
        return self.env['report'].render('sl_general_report.report_trialbalance_sl', docargs)
