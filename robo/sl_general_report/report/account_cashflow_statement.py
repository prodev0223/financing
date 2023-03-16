# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, models, _, tools
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportCashflowStatement(models.AbstractModel):
    _name = 'report.sl_general_report.report_cashflowstatement_sl'

    @api.model
    def _get_account_data(self, account_ids):
        """ Gets account data for the provided account ids"""

        MoveLine = self.env['account.move.line']
        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = MoveLine._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        filters = filters.replace('account_move_line__move_id', 'm').replace('account_move_line', 'l')

        # Get move lines base on sql query and Calculate the total balance of move lines
        sql = ('''
        SELECT 
            l.account_id AS id, 
            aa.code AS code,
            aa.name AS name, 
            l.id AS move_line_id, 
            SUM(COALESCE(l.cashflow_balance, 0)) AS cashflow_balance,
            l.cashflow_activity_id AS cashflow_activity_id
        FROM 
            account_move_line l
        JOIN 
            account_move m ON (l.move_id=m.id)
        JOIN 
            account_account aa ON (l.account_id=aa.id)
        LEFT JOIN 
            res_currency c ON (l.currency_id=c.id)
        LEFT JOIN 
            res_partner p ON (l.partner_id=p.id)
        JOIN 
            account_account acc ON (l.account_id = acc.id)
        WHERE 
            l.cashflow_balance != 0 AND l.account_id IN %s ''' + filters +
               ''' GROUP BY l.account_id, l.cashflow_activity_id, aa.code, aa.name, l.id''')

        params = (tuple(account_ids),) + tuple(where_params)
        new_cursor = self.pool.cursor()
        new_cursor.execute(sql, params)
        account_data = new_cursor.dictfetchall()
        new_cursor.close()
        return account_data

    @api.model
    def _aggregate_data_by_account_and_cashflow_activity(self, account_data):
        move_line_accounts = defaultdict(lambda: defaultdict(lambda: dict()))

        for row in account_data:
            # Determine account and activity
            activity_id = row['cashflow_activity_id']
            if not activity_id:
                activity_id = row['cashflow_activity_id'] = -1  # Update the activity id if it doesn't exist
            account_id = row['id']

            # Move lines of row is the move line if the row has it
            row['move_line_ids'] = [row.pop('move_line_id')] if row['move_line_id'] else []

            # Check if account and cash flow activity id already exists in the move line account data
            data = move_line_accounts[account_id][activity_id]
            if not data:
                data = row
            else:
                # Add move lines to existing cash flow data by activity id and also update the balance
                data['move_line_ids'] += row['move_line_ids']
                data['cashflow_balance'] += row['cashflow_balance']

            move_line_accounts[account_id][activity_id] = data
        return move_line_accounts

    @api.model
    def _process_account_data(self, accounts, cashflow_activity_list, move_line_accounts):
        # Calculate the debit, credit and balance for Accounts
        account_res = {}
        for account in accounts:
            acc_info = {
                'ancestors': dict(),
                'descendants': set()
            }
            base_account_info = {
                'is_view': account.is_view,
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'cashflow_balance': 0.0,
                'move_line_ids': [],
            }
            if account.is_view:
                acc_info.update(base_account_info)

            for activity_id in cashflow_activity_list:
                acc_info_activity = base_account_info.copy()
                cashflow_activity_id = account.cashflow_activity_id.id if account.cashflow_activity_id.id else -1
                acc_info_activity['cashflow_activity_id'] = cashflow_activity_id
                move_line_account_data = move_line_accounts.get(account.id, {})
                if activity_id in move_line_account_data.keys():
                    acc_info_activity['cashflow_balance'] = move_line_account_data[activity_id]['cashflow_balance']
                    acc_info_activity['move_line_ids'] += move_line_account_data[activity_id].get('move_line_ids', [])
                acc_info[activity_id] = acc_info_activity

            account_res[account.id] = acc_info
        return account_res

    @api.model
    def _get_cashflow_account_data(self, cashflow_activity_list, account_res, move_line_accounts, hierarchy_level):
        cashflow_accounts = []

        required_accounts = self.env['account.account'].search([
            '|',
            ('hierarchy_level', '=', hierarchy_level),
            '&',
            ('hierarchy_level', '<', hierarchy_level),
            ('is_view', '=', False)
        ])

        for key in cashflow_activity_list:
            name = _('Pinigų srautai iš ') + \
                   (self.env['cashflow.activity'].browse(key).name if key > 0 else _('Kitų operacijų')) + ' '
            res = {
                'cashflow_balance': 0.0,
                'code': '',
                'name': name,
            }

            r_accounts = []
            r_account_dict = {}
            for r_acc in required_accounts:
                if account_res[r_acc.id][key]['cashflow_balance'] != 0:
                    r_accounts.append(account_res[r_acc.id][key])
                    r_account_dict[r_acc.id] = account_res[r_acc.id][key]

            self.check_if_no_account_missing(move_line_accounts, account_res, r_accounts, key, hierarchy_level)
            res['accounts'] = r_accounts
            for acc in res.get('accounts'):
                if 'ancestors' in account_res[acc['id']].keys():
                    # flag to indicate whether account is represented by its ancestor (that means don't need to sum it)
                    represented = False
                    for ancestor in account_res[acc['id']]['ancestors']:
                        # checks if ancestor is among selected accounts, if so - don't sum it
                        if account_res[ancestor][key] in res['accounts']:
                            represented = True
                            break
                    if represented:
                        continue
                if 'cashflow_balance' in acc.keys():
                    res['cashflow_balance'] += acc['cashflow_balance']

            cashflow_accounts.append(res)

        return cashflow_accounts

    def _get_account_move_entry(self, accounts, hierarchy_level):
        """
        :param:
                accounts: the recordset of accounts

        Returns a dictionary of accounts with following key and value {
                'code': account code,
                'name': account name,
                'debit': sum of total debit amount,
                'credit': sum of total credit amount,
                'balance': total balance,
                'amount_currency': sum of amount_currency,
                'move_lines': list of move line
        }
        """
        cashflow_activities = self.env['cashflow.activity'].search([])
        cashflow_activity_list = cashflow_activities.ids + [-1]  # list of activity types

        account_data = self._get_account_data(accounts.ids)
        move_line_accounts = self._aggregate_data_by_account_and_cashflow_activity(account_data)

        account_res = self._process_account_data(accounts, cashflow_activity_list, move_line_accounts)

        acc_views = self.env['account.account'].with_context(show_views=True).search([
            ('is_view', '=', True)
        ], limit=1, order='hierarchy_level DESC')

        account_hierarchy = acc_views[0].hierarchy_level if acc_views else 11
        for i in range(account_hierarchy, 0, -1):
            self.calculate_view_balance(account_res, i, cashflow_activity_list)

        cashflow_accounts = self._get_cashflow_account_data(
            cashflow_activity_list, account_res, move_line_accounts, hierarchy_level
        )

        return cashflow_accounts

    def check_if_no_account_missing(self, movel_accounts, account_info, r_accounts, activity_id, h_level):
        """
        Function to check if all accounts, that have cashflow balance != 0 is represented. Solves situations when account don't have direct parents.
        Args:
            movel_accounts: accounts from query
            account_info: all account info
            r_accounts: accounts to diplay in report
            activity_id:
            h_level:

        Returns:

        """
        for move in movel_accounts:
            contains = False
            if activity_id in movel_accounts[move].keys():
                for acc in r_accounts:
                    acc_inf = account_info[move]
                    if acc['id'] in acc_inf['ancestors'].keys() or move == acc['id']:
                        contains = True
                        continue
                if not contains: # that means this account is not represented by its ancestors and needs to be added
                    closest_h_level = 100
                    view_id = -1
                    for idx in account_info[move]['ancestors']:
                        ancestor = account_info[move]['ancestors'][idx]
                        if 0 < (ancestor[1] - int(h_level)) < closest_h_level:
                            closest_h_level = ancestor[1] - int(h_level)
                            view_id = ancestor[0]
                    if view_id < 0:
                        view_id = move
                    obj = account_info[view_id][activity_id]
                    r_accounts.append(obj)

    def calculate_view_balance(self, account_list, hierarchy_level, cashflow_activities):
        views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True),
                                                    ('hierarchy_level', '=', hierarchy_level)])


        for view in views:
            children = self.env['account.account'].with_context(show_views=True).search([('parent_id', '=', view.id)])
            cashflow_balance = dict(map(lambda x: (x, 0.0), cashflow_activities))
            if view.id in account_list.keys(): # If view has some journal entries (it shouldn't)
                for activity in cashflow_activities:
                    cashflow_balance[activity] = account_list[view.id][activity]['cashflow_balance']
            for child in children:
                if child.id in account_list.keys():
                    for activity in cashflow_activities:
                        acc_m = account_list[child.id]
                        cashflow_balance[activity] += account_list[child.id][activity]['cashflow_balance']
                        if account_list[child.id][activity]['cashflow_balance'] != 0:
                            for desc in account_list[child.id]['descendants']:
                                account_list[desc]['ancestors'][view.id] = (view.id, view.hierarchy_level) # set yourself as ancestor to your child descendants
                            account_list[child.id]['ancestors'][view.id] = (view.id, view.hierarchy_level) # set yourself as ancestor to your child
                            account_list[view.id]['descendants'] |= account_list[child.id]['descendants']   # pass child's descendants to parent
                            account_list[view.id]['descendants'].add(child.id) # set child as descendant
            if view.id in account_list.keys():
                for activity in cashflow_activities:
                    account_list[view.id][activity]['cashflow_balance'] = cashflow_balance[activity]
        return account_list

    def calculate_cash_bank_balance(self, date_from, date_to):
        cr = self.env.cr
        sql = ("select COALESCE(SUM(balance), 0) as balance\
            from account_move_line aml\
            inner join account_account_type aat on aat.id = aml.user_type_id\
            where date between %s and %s\
            and aat.type = 'liquidity'")
        params = (date_from, date_to)
        cr.execute(sql, params)

        for row in cr.dictfetchall(): # should be only one row
            balance = row['balance']
        return balance

    @api.multi
    def render_html(self, doc_ids, data=None):
        ctx = self._context.copy()
        user = self.env.user
        lang = user.company_id.partner_id.lang if user.company_id.partner_id and user.company_id.partner_id.lang else 'lt_LT'
        ctx['lang'] = self._context.get('force_lang') or lang
        ctx['show_views'] = True
        self = self.with_context(ctx)
        docs = self.env['account.cashflow.report'].browse(self.env.context.get('active_id'))

        accounts = self.env['account.account'].search([])
        accounts_res = self.with_context(data['form'].get('used_context',{}))._get_account_move_entry(accounts, data['form']['hierarchy_level'])
        start_date = (datetime.strptime(data['form']['date_from'], tools.DEFAULT_SERVER_DATE_FORMAT) -
                      relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        beginning_balance = self.calculate_cash_bank_balance('1900-01-01', start_date)
        period_balance = self.calculate_cash_bank_balance(data['form']['date_from'], data['form']['date_to'])
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': 'account.cashflow.report',
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': accounts_res,
            'beginning_balance': beginning_balance,
            'period_balance': period_balance,
            'end_balance': beginning_balance + period_balance
        }
        return self.env['report'].render('sl_general_report.report_cashflowstatement_sl', docargs)

ReportCashflowStatement()
