# -*- coding: utf-8 -*-

import time
from collections import defaultdict

from odoo import api, models, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.sl_general_report.report_generalledger_sl'

    def _get_account_move_entry(self, accounts, init_balance, sortby, display_account, partner_ids, display_partner,
                                sum_by_account):
        """
        :param:
                accounts: the recordset of accounts
                init_balance: boolean value of initial_balance
                sortby: sorting by date or partner and journal
                display_account: type of account(receivable, payable and both)
                sum_by_account: indicator if account entries should be summed

        Returns a dictionary of accounts with following key and value {
                'id': account id,
                'code': account code,
                'name': account name,
                'init_balance': total initial balance,
                'debit': sum of total debit amount,
                'credit': sum of total credit amount,
                'balance': total balance,
                'amount_currency': sum of amount_currency,
                'move_lines': list of move line
        }
        """
        cr = self.env.cr
        MoveLine = self.env['account.move.line']
        move_lines = dict(map(lambda x: (x, []), accounts.ids))

        # Prepare initial sql query and get the initial balance/move lines
        initial_balance = defaultdict(lambda: 0.0)
        if init_balance:
            # Determine dates
            date_from = self.env.context.get('date_from')
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = date_from_dt - relativedelta(days=1)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            init_tables, init_where_clause, init_where_params = MoveLine.with_context(date_to=date_to, date_from=False)._query_get()
            init_wheres = [""]
            if init_where_clause.strip():
                init_wheres.append(init_where_clause.strip())
            init_filters = " AND ".join(init_wheres)
            filters = init_filters.replace('account_move_line__move_id', 'm').replace('account_move_line', 'l')
            if display_partner == 'filter' and partner_ids:
                filters += " AND l.partner_id IN %s"
                init_where_params.append(tuple(partner_ids))
            if sum_by_account:
                select_clause = ''' l.account_id AS account_id,\
                                COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance\
                                '''
            else:
                select_clause = ''' l.account_id AS account_id, '' AS ldate, '' AS lcode,\
                NULL AS amount_currency, '' AS lref, 'Pradinis balansas' AS lname,\
                COALESCE(SUM(l.debit),0.0) AS debit, COALESCE(SUM(l.credit),0.0) AS credit,\
                COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance, '' AS lpartner_id,\
                '' AS move_name, '' AS mmove_id, '' AS currency_code,\
                NULL AS currency_id,\
                '' AS invoice_id, '' AS invoice_type, '' AS invoice_number,\
                '' AS partner_name,\
                array_agg(l.id) AS line_ids\
                '''
            sql = ("SELECT" + select_clause + "FROM account_move_line l\
                LEFT JOIN account_move m ON (l.move_id=m.id)\
                LEFT JOIN res_currency c ON (l.currency_id=c.id)\
                LEFT JOIN res_partner p ON (l.partner_id=p.id)\
                LEFT JOIN account_invoice i ON (m.id =i.move_id)\
                JOIN account_journal j ON (l.journal_id=j.id)\
                WHERE l.account_id IN %s" + filters + ' GROUP BY l.id, l.account_id')
            params = (tuple(accounts.ids),) + tuple(init_where_params)
            cr.execute(sql, params)
            for row in cr.dictfetchall():
                account_id = row.pop('account_id')
                if sum_by_account:
                    initial_balance[account_id] += row['balance']
                else:
                    move_lines[account_id].append(row)

        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = MoveLine._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        filters = filters.replace('account_move_line__move_id', 'm').replace('account_move_line', 'l')
        if display_partner == 'filter' and partner_ids:
            filters += " AND l.partner_id IN %s"
            where_params.append(tuple(partner_ids))
        if sum_by_account:
            select_clause = ''' l.account_id AS account_id, COALESCE(SUM(l.debit),0) AS debit,\
            COALESCE(SUM(l.credit),0) AS credit,COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance\
            '''
            group_by_clause = ''' GROUP BY acc.code, l.account_id'''
            sql_sort = 'acc.code'
        else:
            select_clause = ''' l.id AS lid, l.account_id AS account_id, l.date AS ldate, j.code AS lcode,\
            l.currency_id, l.amount_currency, l.ref AS lref, l.name AS lname, COALESCE(l.debit,0) AS debit,\
            COALESCE(l.credit,0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) AS balance,\
            m.name AS move_name, c.symbol AS currency_code, p.name AS partner_name\
            '''
            group_by_clause = ''' GROUP BY l.id,\
            l.account_id, l.date, j.code, l.currency_id, l.amount_currency, l.ref, l.name, m.name, c.symbol,\
            p.name'''
            sql_sort = 'j.code, p.name, l.move_id' if sortby == 'sort_journal_partner' else 'l.date, l.move_id'
        # Get move lines base on sql query and calculate the total balance of move lines
        sql = ('SELECT' + select_clause + 'FROM account_move_line l\
            JOIN account_move m ON (l.move_id=m.id)\
            LEFT JOIN res_currency c ON (l.currency_id=c.id)\
            LEFT JOIN res_partner p ON (l.partner_id=p.id)\
            JOIN account_journal j ON (l.journal_id=j.id)\
            JOIN account_account acc ON (l.account_id = acc.id) \
            WHERE l.account_id IN %s ' + filters + group_by_clause + '  ORDER BY ' + sql_sort)
        params = (tuple(accounts.ids),) + tuple(where_params)
        cr.execute(sql, params)

        account_res_dict = {}
        account_res = []
        if sum_by_account:
            for row in cr.dictfetchall():
                account_res_dict[row['account_id']] = {
                    'debit': row['debit'],
                    'credit': row['credit'],
                    'balance': row['balance'],
                }

            for account in accounts.filtered(lambda x: not x.is_view):
                currency = account.currency_id and account.currency_id or account.company_id.currency_id
                res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance']) if account.id not in account_res_dict \
                    else account_res_dict[account.id]
                res['code'] = account.code
                res['name'] = account.name
                if init_balance:
                    res['init_balance'] = initial_balance.get(account.id, 0.0)
                    res['balance'] += res['init_balance']
                if display_account in ['all', 'filter']:
                    account_res.append(res)
                    account_res_dict[account.id] = res
                elif display_account == 'movement' and (not currency.is_zero(res['debit']) or
                                                        not currency.is_zero(res['credit']) or
                                                        not currency.is_zero(res['balance'])):
                    account_res.append(res)
                    account_res_dict[account.id] = res
        else:
            for row in cr.dictfetchall():
                balance = 0
                for line in move_lines.get(row['account_id']):
                    balance += line['debit'] - line['credit']
                row['balance'] += balance
                move_lines[row.pop('account_id')].append(row)

            # Calculate the debit, credit and balance for Accounts
            for account in accounts:
                currency = account.currency_id and account.currency_id or account.company_id.currency_id
                res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
                res['code'] = account.code
                res['name'] = account.name
                res['move_lines'] = move_lines[account.id]
                for line in res.get('move_lines'):
                    res['debit'] += line['debit']
                    res['credit'] += line['credit']
                    res['balance'] = line['balance']
                if display_account in ['all', 'filter']:
                    account_res.append(res)
                    account_res_dict[account.id] = res
                elif display_account == 'movement' and res.get('move_lines'):
                    account_res.append(res)
                    account_res_dict[account.id] = res
                elif display_account == 'not_zero' and not currency.is_zero(res['balance']):
                    account_res.append(res)
                    account_res_dict[account.id] = res
            acc_views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True)],
                                                                                         limit=1,
                                                                                         order='hierarchy_level DESC')
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
    def get_html_report_data(self, doc_ids, data=None):
        ctx = self._context.copy()
        user = self.env.user
        ctx['lang'] = user.company_id.partner_id.lang if user.company_id.partner_id and user.company_id.partner_id.lang else 'lt_LT'
        ctx['show_views'] = True
        self = self.with_context(ctx)
        self.model = self.env.context.get('active_model') or u'account.report.general.ledger'
        docs = self.env[self.model].browse(self.env.context.get('active_id'))

        init_balance = data['form'].get('initial_balance', True)
        detail_level = data['form'].get('detail_level', 'detail')
        sortby = data['form'].get('sortby', 'sort_date')
        display_account = data['form']['display_account']
        display_partner = data['form']['display_partner'] if 'display_partner' in data['form'] else 'all'
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in self.env['account.journal'].search([('id', 'in', data['form']['journal_ids'])])]
        if display_account == 'filter':
            accounts = data['form'].get('filtered_account_ids', [])
            if accounts:
                accounts = self.env['account.account'].browse(accounts['filtered_account_ids'])
        else:
            accounts = self.env['account.account'].search([])
        partners = False
        if display_partner == 'filter':
            partners = data['form'].get('filtered_partner_ids', [])
        sum_by_account = detail_level == 'sum'
        accounts_res = self.with_context(data['form'].get('used_context', {}))._get_account_move_entry(
            accounts, init_balance, sortby, display_account, partners, display_partner, sum_by_account)
        return {
            'doc_ids': doc_ids,
            'doc_model': self.model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': accounts_res,
            'print_journal': codes,
        }

    @api.multi
    def render_html(self, doc_ids, data=None):
        docargs = self.get_html_report_data(doc_ids, data)
        return self.env['report'].render('sl_general_report.report_generalledger_sl', docargs)
