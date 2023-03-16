# -*- coding: utf-8 -*-
import datetime
import logging
import time
from collections import defaultdict

from odoo import api, models, tools

_logger = logging.getLogger(__name__)


class ReportFinancial(models.AbstractModel):
    _name = 'report.sl_general_report.report_financial_sl'

    def _compute_account_balance(self, accounts):
        """ compute the balance, debit and credit for the provided accounts
        """
        mapping = {
            'balance': "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance",
            'debit': "COALESCE(SUM(debit), 0) as debit",
            'credit': "COALESCE(SUM(credit), 0) as credit",
        }

        res = defaultdict(lambda: dict((fn, 0.0) for fn in mapping.keys()))

        if not accounts:
            return res

        tables, where_clause, where_params = self.env['account.move.line']._query_get()
        tables = tables.replace('"', '') if tables else "account_move_line"
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        if self._context.get('skip_journal', False):
            wheres.append('account_move_line__move_id.journal_id <> %s')
            where_params.append(self._context.get('skip_journal', False))
        filters = " AND ".join(wheres)

        request = "SELECT account_id as id, array_agg(account_move_line.id) AS move_line_ids, " + ', '.join(mapping.values()) + \
                  " FROM " + tables + \
                  " WHERE account_id IN %s " \
                  + filters + \
                  " GROUP BY account_id"
        params = (tuple(accounts.ids),) + tuple(where_params)

        if not self.env.context.get('archive'):
            new_cursor = self.pool.cursor()
            new_cursor.execute(request, params)
            for row in new_cursor.dictfetchall():
                res[row['id']] = row
            new_cursor.close()
        else:
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                res[row['id']] = row
        return res

    def _compute_report_balance(self, reports):
        '''returns a dictionary with key=the ID of a record and value=the credit, debit and balance amount
           computed for this record. If the record is of type :
               'accounts' : it's the sum of the linked accounts
               'account_type' : it's the sum of leaf accoutns with such an account_type
               'account_report' : it's the amount of the related report
               'sum' : it's the sum of the children of this record (aka a 'view' record)'''
        res = {}
        self = self.with_context(show_views=True)
        fields = ['credit', 'debit', 'balance', 'move_line_ids']
        period_close_journal_id = self.env.user.sudo().company_id.period_close_journal_id
        for report in reports:
            if report.id in res:
                continue
            if report.report_type == 'PL' and period_close_journal_id:
                self = self.with_context(skip_journal=period_close_journal_id.id)
            res[report.id] = dict((fn, 0.0) for fn in fields)
            res[report.id]['move_line_ids'] = []
            report_data = {}
            if report.type == 'accounts':
                # it's the sum of the linked accounts
                all_account_ids = self.get_effective_report_accounts(report)
                account_ids = self.env['account.account'].browse(all_account_ids)
                report_data = self._compute_account_balance(account_ids)
                res[report.id]['account'] = report_data
            elif report.type == 'account_type':
                # it's the sum the leaf accounts with such an account type
                accounts = self.env['account.account'].search([('user_type_id', 'in', report.account_type_ids.ids)])
                report_data = self._compute_account_balance(accounts)
                res[report.id]['account'] = report_data
            elif report.type == 'account_report' and report.account_report_id:
                # it's the amount of the linked report
                report_data = self._compute_report_balance(report.account_report_id)
            elif report.type == 'sum':
                # it's the sum of the children of this account.report
                report_data = self._compute_report_balance(report.children_ids)
            for value in report_data.values():
                for field in fields:
                    field_value = value.get(field)
                    if field_value:
                        res[report.id][field] += field_value
        return res

    @api.model
    def get_effective_report_accounts(self, report):
        def get_child_account_ids(view_accounts):
            child_account_ids = list()
            for view in view_accounts:
                code = view.code
                code = code[:view.hierarchy_level] + '%'
                children_ids = self.env['account.account'].search([('code', '=ilike', code)]).ids
                child_account_ids.extend(children_ids)
            return child_account_ids

        view_account_ids = report.account_ids.filtered(lambda r: r.is_view)
        all_account_ids = report.account_ids.filtered(lambda r: not r.is_view).ids
        all_account_ids.extend(get_child_account_ids(view_account_ids))

        exc_view_account_ids = report.excluded_account_ids.filtered(lambda r: r.is_view)
        exc_all_account_ids = report.excluded_account_ids.filtered(lambda r: not r.is_view).ids
        exc_all_account_ids.extend(get_child_account_ids(exc_view_account_ids))

        all_account_ids = list(set(all_account_ids) - set(exc_all_account_ids))

        return all_account_ids

    def calculate_view_balance(self, account_list, hierarchy_level):
        views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True),
                                                                                  ('hierarchy_level', '=',
                                                                                   hierarchy_level)])
        for view in views:
            children = self.env['account.account'].with_context(show_views=True).search([('parent_id', '=', view.id)])
            for index in account_list:
                debit = 0
                credit = 0
                balance = 0
                balance_cmp = 0
                val = account_list[index]
                if 'account' in val and view.id in val['account']:
                    accounts = val['account']  # it's a dictionary, so we don't copy values!
                    debit = accounts[view.id]['debit']
                    credit = accounts[view.id]['credit']
                    balance = accounts[view.id]['balance']
                    if 'comp_bal' in accounts[view.id].keys():
                        balance_cmp = accounts[view.id]['comp_bal']
                    else:
                        balance_cmp = 0
                for child in children:
                    if 'account' in val and child.id in val['account']:
                        child_data = val['account'][child.id]
                        debit += child_data['debit']
                        credit += child_data['credit']
                        balance += child_data['balance']
                        if 'comp_bal' in child_data.keys():
                            balance_cmp += child_data['comp_bal']
                if 'account' in val and view.id in val['account']:
                    view_data = val['account'][view.id]  # it's a dictionary, so we don't copy !
                    view_data['debit'] = debit
                    view_data['credit'] = credit
                    view_data['balance'] = balance
                    if balance_cmp:
                        view_data['comp_bal'] = balance_cmp
        return account_list

    def get_account_lines(self, data):
        lines = []
        account_report = self.env['account.financial.report'].search([('id', '=', data['account_report_id'][0])])
        get_all_movement = True if data['display_account'] == 'all' else False
        child_reports = account_report._get_children_by_order()
        child_reports = child_reports.sorted(key=lambda r: r.sequence)
        res = self.with_context(data.get('used_context'))._compute_report_balance(child_reports)
        self = self.with_context({'show_views': True})
        if data['enable_filter']:
            comparison_res = self.with_context(data.get('comparison_context'))._compute_report_balance(child_reports)
            for report_id, value in comparison_res.items():
                res[report_id]['comp_bal'] = value['balance']
                report_acc = res[report_id].get('account')
                if report_acc:
                    for account_id, val in comparison_res[report_id].get('account').items():
                        report_acc[account_id]['comp_bal'] = val['balance']

        acc_views = self.env['account.account'].with_context(show_views=True).search([('is_view', '=', True)],
                                                                                     limit=1,
                                                                                     order='hierarchy_level DESC')
        if acc_views:
            account_hierarchy = acc_views[0].hierarchy_level
        else:
            account_hierarchy = 11
        for i in range(account_hierarchy, 0, -1):
            res = self.calculate_view_balance(res, i)
        report_sequence = 0
        for report in child_reports:
            vals = {
                'account_id': report.account_ids.ids[0] if report.account_ids.ids else 0,
                'name': report.name,
                'balance': res[report.id]['balance'] * report.sign,
                'type': 'report',
                'move_line_ids': res[report.id].get('move_line_ids'),
                'level': bool(report.style_overwrite) and report.style_overwrite or report.level,
                'label': report.label,
                'hierarchy_level': 1,
                'account_type': report.type or False,  # used to underline the financial report balances
                'sequence': report_sequence,
                'code': report.code,
            }
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * report.sign

            lines.append(vals)
            if report.display_detail == 'no_detail':
                # the rest of the loop is used to display the details of the financial report, so it's not needed here.
                continue
            if res[report.id].get('account'):
                report_sequence += 1
                for account_id, value in res[report.id]['account'].items():
                    # if there are accounts to display, we add them to the lines with a level equals to their level in
                    # the COA + 1 (to avoid having them with a too low level that would conflicts with the level of data
                    # financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env['account.account'].browse(account_id)
                    name = ''
                    vals = {
                        'account_id': account.id,
                        'code': account.code,
                        'name': name + account.name,
                        'balance': value['balance'] * report.sign or 0.0,
                        'type': 'account',
                        'level': report.display_detail == 'detail_with_hierarchy' and 4,
                        'hierarchy_level': account.hierarchy_level,  # self.get_hierarchy_level(account.code)
                        'account_type': account.internal_type,
                        'sequence': report_sequence,
                    }
                    if data['debit_credit']:
                        vals['debit'] = value['debit']
                        vals['credit'] = value['credit']
                        if not account.company_id.currency_id.is_zero(
                                vals['debit']) or not account.company_id.currency_id.is_zero(vals['credit']):
                            flag = True
                    if not account.company_id.currency_id.is_zero(vals['balance']):
                        flag = True
                    if data['enable_filter']:
                        vals['balance_cmp'] = value['comp_bal'] * report.sign
                        if not account.company_id.currency_id.is_zero(vals['balance_cmp']):
                            flag = True
                    if (flag or get_all_movement) and int(vals['hierarchy_level']) <= int(data['hierarchy_level']):
                        lines.append(vals)
            report_sequence += 1
        return lines

    @api.multi
    def render_html(self, doc_ids, data=None):
        user = self.env.user
        company = user.company_id
        ctx = self._context.copy()
        lang = company.partner_id.lang if company.partner_id.lang else ctx.get('lang')
        ctx.update({'lang': self._context.get('force_lang') or lang, 'show_all': True})
        self = self.with_context(ctx)
        self.model = self.env.context.get('active_model') or u'accounting.report'
        active_id = self.env.context.get('active_id') or 'active_id' in data['form']['used_context'] and data['form']['used_context']['active_id']
        docs = self.env[self.model].browse(active_id).exists()
        if not docs:
            _logger.info('Accounting report: Record does not exist. Model: %s. Record ID: %s' % (self.model, active_id))
            return
        report_lines = self.get_account_lines(data.get('form'))
        report_lines.sort(key=lambda l: (l.get('sequence', 0), l.get('code', '0')))

        data_extend = {}
        data_extend['date_now'] = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        company_title = company.name
        if company.partner_id and company.partner_id.kodas:
            company_title += ', ' + company.partner_id.kodas
        data_extend['company_id'] = [company.id, company_title]
        data_start = data['form']['date_from'] if data['form']['date_from'] else ''
        date_to = data['form']['date_to'] if data['form']['date_to'] else ''
        if docs.account_report_id and docs.account_report_id.report_type == 'BL':
            data_start = company.compute_fiscalyear_dates(
                date=datetime.datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT))['date_from'].\
                strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if data_start and date_to:
            period = data_start + ' - ' + date_to
        elif data_start:
            period = data_start + ' - ' + data_extend['date_now']
        else:
            period = ''

        data_extend['form_period'] = period
        title = data['form']['account_report_id'][1]
        data_extend['form_title'] = title
        data_extend['company_address'] = company.street
        data_extend['company_currency'] = company.currency_id.name
        if company.city and data_extend['company_address']:
            data_extend['company_address'] += ', ' + company.city
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': self.model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_account_lines': report_lines,
            'data_extend': data_extend
        }
        return self.env['report'].render('sl_general_report.report_financial_sl', docargs)
