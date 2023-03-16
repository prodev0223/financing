# -*- coding: utf-8 -*-
from __future__ import division
from odoo.http import Controller, route, request
from odoo import tools, _, exceptions
from json import dumps
from datetime import datetime
from time import mktime
from dateutil.relativedelta import relativedelta

CHART_POSITIVE_COLOR = '#DEF3BA'


def f_round(value, precision=2):
    """Float round the value"""
    return tools.float_round(value, precision_digits=precision)


class Charts(Controller):

    @staticmethod
    def get_bank_end_balance_query(chart_mode=False, subquery_call=False):
        """
        Returns bank end balance query based on the mode
        (Either shown in the chart or banner)
        Select statement of final query and date filtering differs
        between two of the modes, also subquery mode is possible.
        :param chart_mode: Indicates whether the mode is chart or banner
        :param subquery_call: Indicates whether only the subquery should
        be returned
        :return: query (str)
        """

        # Prepare the parameters based on mode
        date_clause = str()
        balance_clause = 'SELECT *'
        if chart_mode:
            date_clause = 'AND A.date <= %(date)s'
            balance_clause = 'SELECT SUM(end_bal_curr)'

        # Subquery of inner join that can be returned separately
        inner_join_subquery = '''
        INNER JOIN
           (SELECT DISTINCT ON (journal_id) *
            FROM (
                SELECT journal_id, A.id AS max_id 
                FROM account_bank_statement as A
                    INNER JOIN account_journal J ON A.journal_id = J.id
                    WHERE A.sepa_imported = TRUE
                      AND J.show_on_dashboard = TRUE {0}
                      AND J.active = TRUE
                      AND J.type = 'bank'
                GROUP BY journal_id, A.id 
                ORDER BY journal_id, date desc, A.id desc) AS foo) abs_grp
            ON AB.journal_id = abs_grp.journal_id
            AND AB.id = abs_grp.max_id
        WHERE date IS NOT NULL
        '''.format(date_clause)
        if subquery_call:
            return inner_join_subquery
        else:
            date_clause = str()
            if chart_mode:
                date_clause = 'AND api_balance_update_date <= %(date)s'
            # Build the whole query
            query = '''WITH non_grouped_data AS ((SELECT
                        id AS journal_id,
                        api_balance_update_date AS update_date,
                        api_end_balance_company_currency AS end_bal_curr,
                        api_end_balance AS end_bal 
                    FROM account_journal
                    WHERE active = TRUE 
                        AND show_on_dashboard = TRUE
                        AND type = 'bank'
                        AND api_balance_update_date IS NOT NULL
                        {2}) 
                    UNION
                    (SELECT AB.journal_id,
                        CASE WHEN date_done IS NOT NULL
                        THEN date_done ELSE date END AS update_date,
                        balance_end_factual_company_currency AS end_bal_curr,
                        balance_end_factual AS end_bal 
                    FROM account_bank_statement AS AB
                    {0}))
                    {1}
                    FROM non_grouped_data ngd
                    INNER JOIN
                        (SELECT journal_id, MAX(update_date) AS max_update_date
                        FROM non_grouped_data
                        GROUP BY journal_id) grouped_data 
                    ON ngd.journal_id = grouped_data.journal_id 
                    AND ngd.update_date = grouped_data.max_update_date'''.format(
                inner_join_subquery, balance_clause, date_clause)
            return query

    @staticmethod
    def get_vat(date_from, date_to):
        """
        Calculate total VAT for given period.
        :param date_from: period date from
        :param date_to: period date to
        :return: VAT amount (float)
        """
        total_taxes = 0.0
        vat_account_ids = request.env.user.sudo().company_id.vat_account_ids.ids
        if vat_account_ids:
            query = '''
            SELECT SUM(account_move_line.balance) AS payable_vat 
                FROM account_move_line
                    JOIN account_move ON account_move_line.move_id = account_move.id
                    WHERE account_move.state = 'posted' 
                    AND account_move_line.date >= %s
                    AND account_move_line.date <= %s 
                    AND account_id in %s'''
            args = (date_from, date_to, tuple(vat_account_ids), )
            request.env.cr.execute(query, args)
            result = request.env.cr.fetchone()
            if result and result[0] is not None:
                total_taxes = f_round(result[0])
        return total_taxes

    def forecast(self, date_end_dt, accumulated_end):
        env = request.env
        close_journal_id = env.user.sudo().company_id.period_close_journal_id.id or 0
        company_id = env.user.sudo().company_id
        du_saskaitos = tuple(company_id._get_payroll_account_ids())

        forecast_cash = []
        if date_end_dt.month == 12:
            forecast_date_start = date_end_dt + relativedelta(years=1, month=1, day=1)
        else:
            forecast_date_start = date_end_dt + relativedelta(month=date_end_dt.month + 1, day=1)
        forecast_date_end = forecast_date_start + relativedelta(months=3)
        stored_forecast_start = forecast_date_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        ind = 0
        static_du = 0
        date_mapping = {}
        accumulated = accumulated_end
        starting_cash_balance = accumulated
        while forecast_date_start <= forecast_date_end:
            f_date = (forecast_date_start + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_mapping[f_date] = ind
            forecast_cash.append({
                'date': f_date,
                'cashflow': 0.0,
                'incomeflow': 0.0,
                'expenseflow': 0.0,
                'diffflow': 0.0,
                'payable_taxes': 0.0,
                'average_factual_taxes': 0.0,
                'forecast_budget_sum': 0.0,
                'expense_du': 0.0,
                'expense_other': 0.0,
                'accumulated_cashflow': starting_cash_balance,
                'forecast': True,
            })
            forecast_date_start += relativedelta(months=1)
            ind += 1
        if forecast_cash and 'cashflow' in forecast_cash[0]:
            forecast_cash[0]['cashflow'] = starting_cash_balance
        # get static salary, we always take full period to avoid lay-off payslips

        average_forecast_income = 0.0
        average_forecast_expenses = 0.0
        average_payable_taxes = 0.0

        average_date_end = datetime.utcnow() - relativedelta(months=1, day=31)
        average_date_start = average_date_end - relativedelta(months=2, day=1)

        # Calculate average payable taxes if user has average options turned on
        if env.user.average_income_forecast and env.user.average_income_forecast:
            payable_taxes = self.get_vat(date_from=average_date_start, date_to=average_date_end)
            # If payable taxes are not negative, set 0
            # P3:DivOK
            average_payable_taxes = f_round(payable_taxes / 3) if tools.float_compare(
                payable_taxes, 0.0, precision_digits=2) > 0 else 0.0

        if env.user.average_income_forecast:
            env.cr.execute('''
            SELECT COALESCE(SUM(amount_total_company_signed), 0) FROM account_invoice 
            WHERE type IN ('out_invoice', 'out_refund')
            AND date_invoice >= %s AND date_invoice <= %s AND state IN ('open', 'paid')
            ''', (average_date_start, average_date_end, ))
            result = env.cr.fetchone()
            if result and result[0] is not None:
                # P3:DivOK
                average_forecast_income = f_round(result[0] / 3)

        if env.user.average_expenses_forecast:
            env.cr.execute('''
            SELECT COALESCE(SUM(amount_total_company_signed), 0) FROM account_invoice 
            WHERE type IN ('in_invoice', 'in_refund')
            AND date_invoice <= %s AND date_invoice >= %s AND state IN ('open', 'paid')
            ''', (average_date_end, average_date_start))
            result = env.cr.fetchone()
            if result and result[0] is not None:
                # P3:DivOK
                average_forecast_expenses = f_round(result[0] / 3)

        if env.user.average_du_forecast:
            prev_salary_start = date_end_dt - relativedelta(months=1, day=1)
            prev_salary_end = date_end_dt - relativedelta(months=1, day=31)
            full_salaries = env['hr.payslip.run'].sudo().search(
                [('date_start', '=', prev_salary_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                 ('state', '=', 'close')], count=True)
            if full_salaries:
                env.cr.execute('''
                        SELECT sum(debit) - sum(credit) as exp
                        FROM account_move_line
                            INNER JOIN account_account on account_move_line.account_id = account_account.id
                            INNER JOIN account_move on account_move_line.move_id = account_move.id
                        WHERE account_account.code like %s and account_move.state = 'posted' and account_move_line.date >= %s 
                        and account_move_line.date <= %s and account_move.journal_id <> %s
                        and account_account.id in %s;
                        ''', ('6%', prev_salary_start, prev_salary_end, close_journal_id, du_saskaitos,))

                result = env.cr.dictfetchall()
            else:
                # during first days of the month we might not have salary computed, so we take even older salaries
                prev_salary_start -= relativedelta(months=1, day=1)
                prev_salary_end -= relativedelta(months=1, day=31)
                env.cr.execute('''
                        SELECT sum(debit) - sum(credit) as exp
                        FROM account_move_line
                            INNER JOIN account_account on account_move_line.account_id = account_account.id
                            INNER JOIN account_move on account_move_line.move_id = account_move.id
                        WHERE account_account.code like %s and account_move.state = 'posted' and account_move_line.date >= %s 
                        and account_move_line.date <= %s and account_move.journal_id <> %s
                        and account_account.id in %s;
                        ''', ('6%', prev_salary_start, prev_salary_end, close_journal_id, du_saskaitos,))
                result = env.cr.dictfetchall()
            for row in result:
                if row['exp'] and not tools.float_is_zero(float(row['exp'] or 0.0), precision_digits=2):
                    static_du += f_round(row['exp'])

        for month in forecast_cash:
            current_month = datetime.strptime(month['date'], tools.DEFAULT_SERVER_DATE_FORMAT)
            next_month = current_month + relativedelta(months=1)
            last_day = (current_month + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            forecast_budget_sum = 0.0

            env.cr.execute("""
            SELECT COALESCE(SUM(expected_amount), 0) AS amt
            FROM forecast_budget_line 
            WHERE user_id = %s 
            AND expected_date >= %s 
            AND expected_date <= %s
            """, (env.user.id, month['date'], last_day))

            result = env.cr.dictfetchall()
            for row in result:
                if row['amt'] and not tools.float_is_zero(float(row['amt'] or 0.0), precision_digits=2):
                    forecast_budget_sum += f_round(row['amt'])

            if tools.float_compare(forecast_budget_sum, 0.0, precision_digits=2) > 0:
                month['incomeflow'] += forecast_budget_sum
            elif tools.float_compare(forecast_budget_sum, 0.0, precision_digits=2) < 0:
                month['expenseflow'] += forecast_budget_sum

            if env.user.include_income:
                # Income >
                env.cr.execute("""SELECT COALESCE(SUM(residual_signed), 0) AS income
                                                FROM account_invoice WHERE residual <> 0 and date_due >= %s and date_due < %s AND type 
                                                IN ('out_invoice', 'out_refund') AND state IN ('open', 'paid', 'proforma', 'proforma2')
                                                                """, (current_month, next_month,))
                result = env.cr.dictfetchall()
                for row in result:
                    if row['income'] and not tools.float_is_zero(float(row['income'] or 0.0), precision_digits=2):
                        month['incomeflow'] += f_round(row['income'])
            month['incomeflow'] += average_forecast_income

            if env.user.include_expenses:
                # Expense >
                env.cr.execute("""SELECT COALESCE(SUM(residual_signed), 0) AS expense
                                                FROM account_invoice WHERE residual <> 0 and date_due >= %s and date_due < %s AND type 
                                                IN ('in_invoice', 'in_refund') AND state IN ('open', 'paid', 'proforma', 'proforma2')
                                                                """, (current_month, next_month,))

                result = env.cr.dictfetchall()
                for row in result:
                    if row['expense'] and not tools.float_is_zero(float(row['expense'] or 0.0), precision_digits=2):
                        month['expense_other'] += f_round(-row['expense'])
                        month['expenseflow'] += f_round(-row['expense'])
            month['expenseflow'] -= average_forecast_expenses

            # Calculate factual payable taxes for future forecast
            payable_taxes = self.get_vat(
                date_from=current_month - relativedelta(months=1, day=1),
                date_to=current_month - relativedelta(months=1, day=31))
            # If payable taxes are not negative, set 0
            payable_taxes = payable_taxes if tools.float_compare(payable_taxes, 0.0, precision_digits=2) > 0 else 0.0

            month['expense_du'] = -static_du
            month['payable_taxes'] = payable_taxes
            month['average_factual_taxes'] = average_payable_taxes
            month['forecast_budget_sum'] = forecast_budget_sum
            month['expenseflow'] += payable_taxes
            month['expenseflow'] += -static_du
            month['cashflow'] += month['incomeflow'] + month['expenseflow']
            accumulated += month['cashflow']
            month['accumulated_cashflow'] = accumulated

        # sum up overdue amounts
        if env.user.include_income:
            overdue_amount_income = 0.0

            env.cr.execute("""
            SELECT COALESCE(SUM(residual_signed), 0) AS balance
            FROM account_invoice
            WHERE residual <> 0
              AND type IN ('out_invoice', 'out_refund')
              AND date_due < %s
              AND state IN ('open', 'paid')
                           """, (stored_forecast_start,))

            result = env.cr.dictfetchall()
            for row in result:
                if row['balance'] and not tools.float_is_zero(float(row['balance'] or 0.0), precision_digits=2):
                    overdue_amount_income += f_round(row['balance'])

            if not tools.float_is_zero(overdue_amount_income, precision_digits=2):
                accumulated += overdue_amount_income
                forecast_cash[0]['cashflow'] += overdue_amount_income
                forecast_cash[0]['accumulated_cashflow'] += overdue_amount_income
                forecast_cash[0]['incomeflow'] += overdue_amount_income

        if env.user.include_expenses:
            overdue_amount_expenses = 0.0
            env.cr.execute("""
            SELECT COALESCE(SUM(-residual_signed), 0) AS balance
            FROM account_invoice
            WHERE residual <> 0
              AND type IN ('in_invoice', 'in_refund')
              AND date_due < %s
              AND state IN ('open', 'paid')
                           """, (stored_forecast_start,))

            result = env.cr.dictfetchall()
            for row in result:
                if row['balance'] and not tools.float_is_zero(float(row['balance'] or 0.0), precision_digits=2):
                    overdue_amount_expenses += f_round(row['balance'])

            if not tools.float_is_zero(overdue_amount_expenses, precision_digits=2):
                accumulated += overdue_amount_expenses
                forecast_cash[0]['cashflow'] += overdue_amount_expenses
                forecast_cash[0]['accumulated_cashflow'] += overdue_amount_expenses
                forecast_cash[0]['incomeflow'] += overdue_amount_expenses

        accumulated -= starting_cash_balance
        return forecast_cash, accumulated

    def get_currency(self):
        return request.env.user.company_id.currency_id.name

    def get_currency_symbol(self):
        return request.env.user.company_id.currency_id.symbol

    def get_cashflow(self, date=None):
        """
        Old get_cashflow method is renamed to get_cashflow_accounting, which calculates bank chart data
         based on account_move_lines.
        This new implementation of get_cashflow calculates bank chart data based on account_bank_statement_lines
        :return: bank chart data
        """
        if date is None:
            date = {'start': '2018-01-01', 'end': '2018-12-31'}
        env = request.env
        if not env.user.is_manager():
            return dumps(False)
        cashflow = []
        date_start = date['start']
        date_end = date['end']
        date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_start_dt > date_end_dt:
            date_end_dt = date_start_dt
        date_mapping = {}
        index = 0
        while date_start_dt <= date_end_dt:
            date = (date_start_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_mapping[date] = index
            cashflow.append({
                'date': date,
                'cashflow': 0.0,
                'incomeflow': 0.0,
                'expenseflow': 0.0,
                'diffflow': 0.0,
                'accumulated_cashflow': 0.0,
                'percentage': 0,
                'payable_taxes': 0
            })
            date_start_dt += relativedelta(day=31) + relativedelta(days=1)
            index += 1

        accumulated_cash = 0.0
        accumulated_cash_accounting = 0.0

        # Use datetime (last second of the day) since balance update date is datetime
        date_end_tm = (datetime.strptime(
            date_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
            hour=23, minute=59, second=59)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        # Get latest (factual) balance data
        env.cr.execute(self.get_bank_end_balance_query(chart_mode=True), {'date': date_end_tm, })
        latest_balance_data = env.cr.fetchone()
        if latest_balance_data and latest_balance_data[0] is not None:
            accumulated_cash = f_round(latest_balance_data[0])

        # Get latest (only accounting) balance data
        accounting_balance_query = '''SELECT
            SUM(AB.balance_end_factual_company_currency)  
            FROM account_bank_statement AS AB
            INNER JOIN account_journal ON AB.journal_id = account_journal.id
            ''' + self.get_bank_end_balance_query(chart_mode=True, subquery_call=True) + '''
            AND account_journal.type = 'bank'
            AND AB.sepa_imported = true'''

        env.cr.execute(accounting_balance_query, {'date': date_end, })
        accounting_balance_data = env.cr.fetchone()
        if accounting_balance_data and accounting_balance_data[0] is not None:
            accumulated_cash_accounting = f_round(accounting_balance_data[0])

        env.cr.execute('''
                SELECT
                  SUM(income) AS income, SUM(expense) AS expense, SUM(expense) + SUM(income) AS cashflow, 
                  SUM(st_bal) AS st_bal, SUM(end_bal), date_trunc('month', foo.date) AS month
                  FROM (
                        SELECT account_bank_statement_line.date, 
                        account_bank_statement.balance_start_currency as st_bal, 
                        account_bank_statement.balance_end_currency as end_bal,
                        SUM((CASE
                            WHEN amount_company_currency > 0 THEN amount_company_currency
                            ELSE 0
                        END)) + sum((CASE
                            WHEN amount_company_currency < 0 THEN amount_company_currency
                            ELSE 0
                        END)) as cashflow,
                        SUM((CASE
                            WHEN amount_company_currency < 0 THEN amount_company_currency
                            ELSE 0
                        END)) as expense, sum((CASE
                            WHEN amount_company_currency > 0 THEN amount_company_currency
                            ELSE 0
                        END)) as income
                        FROM account_bank_statement_line
                            INNER JOIN account_journal ON account_bank_statement_line.journal_id = account_journal.id
                            INNER JOIN account_bank_statement ON account_bank_statement_line.statement_id = 
                            account_bank_statement.id
                        WHERE account_journal.type = 'bank' 
                        AND account_journal.show_on_dashboard = true 
                        AND account_journal.active = true 
                        AND account_bank_statement_line.date >= %s
                        AND account_bank_statement_line.date <= %s
                        AND account_bank_statement.sepa_imported = true
                        AND account_bank_statement_line.sepa_duplicate = false
                        AND (partner_id <> 1 OR partner_id IS NULL)
                        GROUP BY account_bank_statement_line.date, account_bank_statement.balance_start_currency, 
                        account_bank_statement.balance_end_currency, account_bank_statement.journal_id
                        ORDER BY account_bank_statement_line.date
                ) as foo GROUP BY month
        ''', (date_start, date_end,))
        res = env.cr.dictfetchall()
        for line in res:
            date = line['month'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            cashflow[date_mapping[date]]['cashflow'] += f_round(line['cashflow'])
            cashflow[date_mapping[date]]['incomeflow'] += f_round(line['income'])
            cashflow[date_mapping[date]]['expenseflow'] += f_round(line['expense'])
            cashflow[date_mapping[date]]['diffflow'] += f_round(line['income'] + line['expense'])
        st_start = accumulated_cash

        diff = accumulated_cash - accumulated_cash_accounting
        for en, cash in enumerate(reversed(cashflow), 1):
            cash['accumulated_cashflow'] = st_start
            if en == 1:
                # Calculate payable taxes for last month from previous month data
                date_dt = datetime.strptime(cash['date'], tools.DEFAULT_SERVER_DATE_FORMAT)
                payable_taxes = self.get_vat(
                    date_from=date_dt - relativedelta(months=1, day=1),
                    date_to=date_dt - relativedelta(months=1, day=31))
                # If payable taxes are not negative, set 0
                cash['payable_taxes'] = payable_taxes if tools.float_compare(payable_taxes, 0.0,
                                                                             precision_digits=2) > 0 else 0.0
                if not tools.float_is_zero(diff, precision_digits=2):
                    # recompute amounts
                    if tools.float_compare(0.0, diff, precision_digits=2) > 0:
                        cash['expenseflow'] += diff
                    else:
                        cash['incomeflow'] += diff
                    balance = cash['expenseflow'] + cash['incomeflow']
                    cash['cashflow'] = cash['diffflow'] = balance
            if en == len(cashflow):
                cash['cashflow'] = st_start
            st_start -= cash['cashflow']

        currency_symbol = self.get_currency_symbol()
        index = 0
        for en, line in enumerate(cashflow):
            if index:
                # P3:DivOK
                rate = abs(cashflow[en - 1]['cashflow'] / 100)
                diff = cashflow[en]['cashflow'] - cashflow[en - 1]['cashflow']
                if rate:
                    # P3:DivOK
                    cashflow[en]['percentage'] = int(round(diff / rate, 0))
            index += 1
        if date_end_dt.month == datetime.now().month and \
                date_end_dt.year == datetime.now().year and \
                env.user.show_cash_forecast:
            forecast, accumulated_forecast = self.forecast(date_end_dt, cashflow[-1]['accumulated_cashflow'])
            cashflow = accumulated_cash = False
            return forecast, accumulated_forecast, cashflow, accumulated_cash, currency_symbol
        else:
            forecast = accumulated_forecast = False
            return forecast, accumulated_forecast, cashflow, accumulated_cash, currency_symbol

    def get_cashflow_accounting(self, date={'start': '2018-01-01', 'end': '2018-12-31'}):
        # TODO: """METHOD NOT USED ANYMORE"""
        if not request.env.user.is_manager():
            return dumps(False)
        cashflow = []
        env = request.env
        if not env.user.is_manager():
            raise exceptions.AccessDenied()
        liquidity_type = env.ref('account.data_account_type_liquidity')
        if liquidity_type:
            liquidity_type = liquidity_type.id
        date_start = date['start']
        date_end = date['end']
        date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_start_dt > date_end_dt:
            date_end_dt = date_start_dt

        date_mapping = {}
        index = 0
        while date_start_dt <= date_end_dt:
            date = (date_start_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_mapping[date] = index
            cashflow.append({
                'date': date,
                'cashflow': 0.0,
                'incomeflow': 0.0,
                'expenseflow': 0.0,
                'diffflow': 0.0,
                'accumulated_cashflow': 0.0,
                'percentage': 0,
            })
            date_start_dt += relativedelta(day=31) + relativedelta(days=1)
            index += 1
        env.cr.execute('''
        SELECT
          sum(cashflow) as cashflow, sum(income) as income, sum(expense) as expense, 
          date_trunc('month', foo.date) AS month
          FROM (
                SELECT account_move_line.date, sum(debit) - sum(credit) as cashflow, sum(debit) as income, sum(credit) as expense 
                FROM account_move_line
                    INNER JOIN account_account on account_move_line.account_id = account_account.id
                    INNER JOIN account_move on account_move_line.move_id = account_move.id
                WHERE account_account.user_type_id = %s and account_account.code like '271%%' and state = 'posted' and account_move_line.date >= %s and account_move_line.date <= %s
                GROUP BY account_move_line.date
        ) as foo GROUP BY month;
''', (liquidity_type, date_start, date_end,))
        res = env.cr.dictfetchall()
        for line in res:
            date = line['month'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            cashflow[date_mapping[date]]['cashflow'] += line['cashflow']
            cashflow[date_mapping[date]]['incomeflow'] += line['income']
            cashflow[date_mapping[date]]['expenseflow'] += line['expense']
            cashflow[date_mapping[date]]['diffflow'] += line['income'] - line['expense']
        env.cr.execute('''
                SELECT sum(debit) - sum(credit) as cashflow 
                FROM account_move_line
                    INNER JOIN account_account on account_move_line.account_id = account_account.id
                    INNER JOIN account_move on account_move_line.move_id = account_move.id
                WHERE account_account.user_type_id = %s  and account_account.code like '271%%' and state = 'posted' and account_move_line.date < %s;
    ''', (liquidity_type, date_start,))
        res = env.cr.fetchone()
        if res and res[0]:
            accumulated_cash = res[0]
        else:
            accumulated_cash = 0.0
        first = True
        for cash in cashflow:
            accumulated_cash += cash['cashflow']
            cash['accumulated_cashflow'] = accumulated_cash
            if first:
                first = False
                cash['cashflow'] = accumulated_cash
        currency_symbol = self.get_currency_symbol()

        index = 0
        for en, line in enumerate(cashflow):
            if index:
                # P3:DivOK
                rate = abs(cashflow[en - 1]['cashflow'] / 100)
                diff = cashflow[en]['cashflow'] - cashflow[en - 1]['cashflow']
                if rate:
                    # P3:DivOK
                    cashflow[en]['percentage'] = int(round(diff / rate, 0))
            index += 1

        if date_end_dt.month == datetime.now().month and \
                date_end_dt.year == datetime.now().year and \
                env.user.show_cash_forecast:
            forecast, accumulated_forecast = self.forecast(date_end_dt, cashflow[-1]['accumulated_cashflow'])
            cashflow = accumulated_cash = False
            return forecast, accumulated_forecast, cashflow, accumulated_cash, currency_symbol
        else:
            forecast = accumulated_forecast = False
            return forecast, accumulated_forecast, cashflow, accumulated_cash, currency_symbol

    def get_pajamos(self, date=None):
        if date is None:
            date = {'start': '2018-01-01', 'end': '2018-12-31'}
        mode = False
        if request.env.user.has_group('robo_basic.group_robo_see_income'):
            mode = 'user'
        if request.env.user.is_manager()\
                or request.env.user.has_group('robo.group_robo_see_all_incomes')\
                or request.env.user.has_group('robo.group_menu_kita_analitika'):
            if request.env.user.show_only_personal_income:
                mode = 'user'
            else:
                mode = 'manager'
        if not mode:
            return dumps(False)
        pajamos = []
        date_start = date['start']
        date_end = date['end']
        date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_start_dt > date_end_dt:
            date_end_dt = date_start_dt
        date_mapping = {}
        index = 0
        while date_start_dt <= date_end_dt:
            date = (date_start_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_mapping[date] = index
            pajamos.append({
                'date': date,
                'inc': 0.0,
                'exp': 0.0,
                'percentage': 0
            })
            date_start_dt += relativedelta(day=31) + relativedelta(days=1)
            index += 1
        env = request.env
        # if not env.user.is_manager():
        #     raise exceptions.AccessDenied()
        close_journal_id = env.user.sudo().company_id.period_close_journal_id.id or 0

        if mode == 'manager':
            env.cr.execute('''
            SELECT SUM(inc) AS inc
                 , SUM(exp) AS exp
                 , date_trunc('month', foo.date) AS month
            FROM (SELECT aml.date
                       , SUM(credit) - SUM(debit) AS inc
                       , 0.0 AS exp
                  FROM account_move_line aml
                  INNER JOIN account_account ON aml.account_id = account_account.id
                  INNER JOIN account_move ON aml.move_id = account_move.id
                  WHERE account_account.code like %s
                    AND state = 'posted'
                    AND aml.date >= %s 
                    AND aml.date <= %s
                    AND account_move.journal_id <> %s
                  GROUP BY aml.date
            ) AS foo
            GROUP BY month;
            ''', ('5%', date_start, date_end, close_journal_id))
        else:
            env.cr.execute('''
            SELECT SUM(inc) AS inc
                 , SUM(exp) AS exp
                 , date_trunc('month', foo.date) AS month
            FROM (SELECT aml.date
                       , SUM(credit) - SUM(debit) AS inc
                       , 0.0 AS exp
                  FROM account_move_line aml
                  INNER JOIN account_account ON aml.account_id = account_account.id
                  INNER JOIN account_move ON aml.move_id = account_move.id
                  INNER JOIN account_invoice inv ON aml.invoice_id = inv.id
                  WHERE account_account.code like %s
                    AND account_move.state = 'posted'
                    AND aml.date >= %s 
                    AND aml.date <= %s
                    AND account_move.journal_id <> %s
                    AND inv.user_id = %s
                  GROUP BY aml.date
            ) AS foo
            GROUP BY month;
            ''', ('5%', date_start, date_end, close_journal_id, request.env.user.id))

        res = env.cr.dictfetchall()
        for line in res:
            date = line['month'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            pajamos[date_mapping[date]]['inc'] += f_round(line['inc'])

        index = 0
        for en, line in enumerate(pajamos):
            if index:
                # P3:DivOK
                rate = abs(pajamos[en - 1]['inc'] / 100)
                diff = pajamos[en]['inc'] - pajamos[en - 1]['inc']
                if rate:
                    # P3:DivOK
                    pajamos[en]['percentage'] = int(round(diff / rate, 0))
            index += 1
        currency_symbol = self.get_currency_symbol()
        return pajamos, currency_symbol

    def get_pelnas(self, date=None, expense_calc=False):
        if date is None:
            date = {'start': '2018-01-01', 'end': '2018-12-31'}
        if not request.env.user.is_manager():
            return dumps(False)
        pajamos = []
        date_start = date['start']
        date_end = date['end']
        date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_start_dt > date_end_dt:
            date_end_dt = date_start_dt
        date_mapping = {}
        index = 0
        while date_start_dt <= date_end_dt:
            date = (date_start_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_mapping[date] = index
            pajamos.append({
                'date': date,
                'inc': 0.0,
                'exp': 0.0,
                'percentage': 0,
            })
            date_start_dt += relativedelta(day=31) + relativedelta(days=1)
            index += 1
        env = request.env
        if not env.user.is_manager():
            raise exceptions.AccessDenied()
        close_journal_id = env.user.sudo().company_id.period_close_journal_id.id or 0
        env.cr.execute('''
        SELECT SUM(inc) AS inc
             , SUM(exp) AS exp
             , date_trunc('month', foo.date) AS month
        FROM ((
                SELECT aml.date
                     , SUM(credit) - SUM(debit) AS inc
                     , 0.0 AS exp
                FROM account_move_line aml
                    INNER JOIN account_account ON aml.account_id = account_account.id
                    INNER JOIN account_move move ON aml.move_id = move.id
                WHERE account_account.code LIKE %s
                  AND move.state = 'posted'
                  AND aml.date >= %s 
                  AND aml.date <= %s
                  AND move.journal_id <> %s
                GROUP BY aml.date
              )
              UNION
              (
                SELECT aml.date, 0.0 as inc, sum(debit) - sum(credit) as exp
                FROM account_move_line aml
                    INNER JOIN account_account ON aml.account_id = account_account.id
                    INNER JOIN account_move move ON aml.move_id = move.id
                WHERE account_account.code LIKE %s
                  AND move.state = 'posted'
                  AND aml.date >= %s 
                  AND aml.date <= %s
                  AND move.journal_id <> %s
                GROUP BY aml.date
              )
             ) AS foo
        GROUP BY month;
        ''', ('5%', date_start, date_end, close_journal_id, '6%', date_start, date_end, close_journal_id,))
        res = env.cr.dictfetchall()
        for line in res:
            date = line['month'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            pajamos[date_mapping[date]]['inc'] += f_round(line['inc'])
            pajamos[date_mapping[date]]['exp'] += f_round(line['exp'])

        if expense_calc:
            for en, line in enumerate(pajamos):
                if en:
                    current = pajamos[en]['exp']
                    prev = pajamos[en - 1]['exp']
                    # P3:DivOK
                    rate = abs(prev / 100)
                    diff = current - prev
                    if rate:
                        # P3:DivOK
                        pajamos[en]['percentage'] = int(round(diff / rate, 0))
        else:
            for en, line in enumerate(pajamos):
                if en:
                    current = pajamos[en]['inc'] - pajamos[en]['exp']
                    prev = pajamos[en - 1]['inc'] - pajamos[en - 1]['exp']
                    # P3:DivOK
                    rate = abs(prev / 100)
                    diff = current - prev
                    if rate:
                        pajamos[en]['percentage'] = int(round(diff / rate, 0))

        currency_symbol = self.get_currency_symbol()
        return pajamos, currency_symbol

    def get_income_comparison(self, date=None):
        if date is None:
            date = {'start': '2018-01-01', 'end': '2018-12-31'}
        colors = {'#E6B0AA', '#B0E6AA', '#B0AAE6','#E6AAB0', '#DF99CC',
                  '#DFC9C9', '#DFCC99', '#99CCDF', '#AACCD6', '#AAD6CC'}
        if not request.env.user.has_group('robo_basic.group_view_income_compare_chart'):
            return dumps(False)
        date_start = date['start']
        date_end = date['end']
        env = request.env
        close_journal_id = env.user.sudo().company_id.period_close_journal_id.id or 0
        env.cr.execute('''
        SELECT SUM(inc) AS inc
             , salesman
             , color
        FROM (SELECT SUM(credit) - SUM(debit) AS inc
                   , partner.display_name AS salesman
                   , partner.color AS color
              FROM account_move_line aml
                  INNER JOIN account_account ON aml.account_id = account_account.id
                  INNER JOIN account_move ON aml.move_id = account_move.id
                  INNER JOIN account_invoice inv ON aml.invoice_id = inv.id
                  INNER JOIN res_users users ON users.id = inv.user_id
                  INNER JOIN res_partner partner ON partner.id = users.partner_id
              WHERE account_account.code LIKE %s
                AND account_move.state = 'posted'
                AND aml.date >= %s 
                AND aml.date <= %s
                AND account_move.journal_id <> %s
              GROUP BY aml.date, salesman, color
        ) AS foo
        GROUP BY salesman, color
        ORDER BY inc DESC;
        ''', ('5%', date_start, date_end, close_journal_id,))
        res = env.cr.dictfetchall()

        incomes = [{'value': line['inc'] or 0.0,
                    'color': line['color'] or colors.pop() if colors else '#B0C6CC',
                    'icon': 'icon-man2',
                    'name': line['salesman'],
                    'id': line['salesman'],} for line in res]

        currency_symbol = self.get_currency_symbol()
        return incomes, currency_symbol

    def get_expenses(self, date=None):
        if date is None:
            date = {'start': '2018-01-01', 'end': '2018-12-31'}
        mode = False
        if request.env.user.has_group('robo_basic.group_robo_see_income') \
                or request.env.user.is_premium_user():
            mode = 'user'
        if request.env.user.is_manager():
            mode = 'manager'
        if not mode:
            return dumps(False)
        expenses = []
        date_start = date['start']
        date_end = date['end']
        env = request.env
        if mode == 'manager' and not env.user.is_manager():
            raise exceptions.AccessDenied()

        close_journal_id = env.user.sudo().company_id.period_close_journal_id.id or 0
        company_id = env.user.sudo().company_id
        payroll_accounts = company_id._get_payroll_expense_account_ids()
        depreciation_account_ids = env['account.account'].search([('user_type_id', '=', env.ref('account.data_account_type_depreciation').id)]).ids
        skip_accounts = payroll_accounts + depreciation_account_ids
        du_saskaitos = tuple(payroll_accounts)
        depreciation_account_ids = tuple(depreciation_account_ids)
        skip_accounts = tuple(skip_accounts)
        employee_id = request.env.user.employee_ids[0].id if request.env.user.employee_ids else 0

        if mode == 'manager':
            env.cr.execute('''
            SELECT sum(exp) AS exp
                 , icon
                 , color
                 , name
                 , cat_id
            FROM (
                SELECT SUM(debit) - SUM(credit) AS exp
                     , product_category.ultimate_icon AS icon
                     , product_category.ultimate_color AS color
                     , product_category.ultimate_name AS name
                     , product_category.ultimate_id AS cat_id
                FROM account_move_line aml
                    INNER JOIN account_account ON aml.account_id = account_account.id
                    INNER JOIN account_move ON aml.move_id = account_move.id
                     LEFT JOIN product_product ON aml.product_id = product_product.id
                     LEFT JOIN product_template ON product_product.product_tmpl_id = product_template.id
                     LEFT JOIN product_category ON product_template.categ_id = product_category.id
                WHERE account_account.code LIKE %s
                  AND account_move.state = 'posted'
                  AND aml.date >= %s
                  AND aml.date <= %s
                  AND account_move.journal_id <> %s
                  AND account_account.id NOT IN %s
                GROUP BY product_category.ultimate_icon, product_category.ultimate_color
                       , product_category.ultimate_name, product_category.ultimate_id
                    ) AS foo
            GROUP BY icon, color, name, cat_id;
            ''', ('6%', date_start, date_end, close_journal_id, skip_accounts,))
        else:
            env.cr.execute('''
            SELECT sum(exp) AS exp
                 , icon
                 , color
                 , name
                 , cat_id
            FROM (
                SELECT SUM(debit) - SUM(credit) AS exp
                     , product_category.ultimate_icon AS icon
                     , product_category.ultimate_color AS color
                     , product_category.ultimate_name AS name
                     , product_category.ultimate_id AS cat_id
                FROM account_move_line aml
                    INNER JOIN account_account ON aml.account_id = account_account.id
                    INNER JOIN account_move ON aml.move_id = account_move.id
                     LEFT JOIN product_product ON aml.product_id = product_product.id
                     LEFT JOIN product_template ON product_product.product_tmpl_id = product_template.id
                     LEFT JOIN product_category ON product_template.categ_id = product_category.id
                    INNER JOIN account_invoice inv ON aml.invoice_id = inv.id
                WHERE account_account.code LIKE %s
                  AND account_move.state = 'posted'
                  AND aml.date >= %s
                  AND aml.date <= %s
                  AND account_move.journal_id <> %s
                  AND account_account.id NOT IN %s
                  AND (inv.user_id = %s OR (inv.submitted_employee_id = %s AND inv.submitted_employee_id <> Null))
                GROUP BY product_category.ultimate_icon, product_category.ultimate_color
                       , product_category.ultimate_name, product_category.ultimate_id
                    ) AS foo
            GROUP BY icon, color, name, cat_id;
            ''', ('6%', date_start, date_end, close_journal_id, skip_accounts, request.env.user.id, employee_id,))

        res = env.cr.dictfetchall()
        names = {c.id: c.name for c in env['product.category'].browse([i for i in map(lambda x: x.get('cat_id'), res) if i])}
        expenses.extend([{
            'value': f_round(line['exp'] or 0.0),
            'color': line['color'] or '#E6B0AA',
            'icon': line['icon'] or 'icon-cart-full',
            'name': names.get(line['cat_id']) or _('Kitos įvairios išlaidos'),
            'id': line['cat_id'] or 'Kita',
        } for line in res if line['exp'] and not tools.float_is_zero(float(line['exp'] or 0.0), precision_digits=2)])

        if mode == 'manager' and du_saskaitos:
            # Payroll
            env.cr.execute('''
            SELECT SUM(debit) - SUM(credit) AS exp
            FROM account_move_line aml
                INNER JOIN account_account ON aml.account_id = account_account.id
                INNER JOIN account_move ON aml.move_id = account_move.id
            WHERE account_account.code LIKE %s
              AND account_move.state = 'posted'
              AND aml.date >= %s
              AND aml.date <= %s
              AND account_move.journal_id <> %s
              AND account_account.id IN %s;
            ''', ('6%', date_start, date_end, close_journal_id, du_saskaitos,))

            res = env.cr.dictfetchall()
            expenses.extend([{
                'value': f_round(line['exp'] or 0.0),
                'color': '#6699ff',
                'icon': 'icon-man2',
                'name': _('Darbo užmokesčio sąnaudos'),
                'id': 'DU'
            } for line in res if line['exp'] and not tools.float_is_zero(float(line['exp'] or 0.0), precision_digits=2)])
            # Depreciation
            env.cr.execute('''
                        SELECT SUM(debit) - SUM(credit) AS exp
                        FROM account_move_line aml
                            INNER JOIN account_account ON aml.account_id = account_account.id
                            INNER JOIN account_move ON aml.move_id = account_move.id
                        WHERE account_account.code LIKE %s
                          AND account_move.state = 'posted'
                          AND aml.date >= %s
                          AND aml.date <= %s
                          AND account_move.journal_id <> %s
                          AND account_account.id IN %s;
                        ''', ('6%', date_start, date_end, close_journal_id, depreciation_account_ids,))

            res = env.cr.dictfetchall()
            expenses.extend([{
                'value': f_round(line['exp'] or 0.0),
                'color': '#bc51b3',
                'icon': 'icon-broom',
                'name': _('Nusidėvėjimas'),
                'id': 'DEPR'
            } for line in res if
                line['exp'] and not tools.float_is_zero(float(line['exp'] or 0.0), precision_digits=2)])
        currency_symbol = self.get_currency_symbol()
        return expenses, currency_symbol

    def get_amounts(self, expenses, invoice_data, mode, date=False):
        if not date:
            date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)  # Today

        data_set = []
        data_filter = 'IS NOT NULL' if invoice_data else 'IS NULL'
        top_all = 0.0
        limit = 4
        env = request.env
        top_overdue = 0.0
        if expenses:
            top_order = 'ORDER BY residual ASC'
        else:
            top_order = 'ORDER BY residual DESC'
        if not invoice_data:
            if mode == 'manager':
                env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                       , COUNT(l.amount_residual) AS total_count
                                  FROM account_move_line l
                                    LEFT JOIN account_account a ON l.account_id = a.id
                                    LEFT JOIN account_account_type act ON a.user_type_id = act.id
                                    LEFT JOIN account_move m ON l.move_id = m.id
                                  WHERE
                                      CASE WHEN %s THEN 
                                        act.type IN ('payable')
                                      ELSE
                                        act.type IN ('receivable')
                                      END
                                    AND l.reconciled IS FALSE
                                    AND l.invoice_id {}
                                    AND m.state = 'posted'
                               """.format(data_filter), (expenses, ))
                data = env.cr.fetchone()
            elif not expenses:
                env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                       , COUNT(l.amount_residual) AS total_count
                                  FROM account_move_line l
                                    LEFT JOIN account_account a ON l.account_id = a.id
                                    LEFT JOIN account_account_type act ON a.user_type_id = act.id
                                    LEFT JOIN account_invoice inv ON inv.id = l.invoice_id
                                    LEFT JOIN account_move m ON l.move_id = m.id
                                  WHERE
                                      CASE WHEN %s THEN 
                                        act.type IN ('payable')
                                      ELSE
                                        act.type IN ('receivable')
                                      END
                                    AND l.reconciled IS FALSE
                                    AND l.invoice_id {}
                                    AND m.state = 'posted'
                                    AND inv.user_id = %s
                               """.format(data_filter), (expenses, request.env.user.id,))
                data = env.cr.fetchone()
            else:
                data = []

            if data:
                total_overdue = f_round((data[0] or 0.0) * (-1.0 if expenses else 1.0))
                total_overdue_count = f_round(data[1] or 0.0)
            else:
                total_overdue = 0.0
                total_overdue_count = 0
            return total_overdue, total_overdue_count

        # Top overdue
        if mode == 'manager':
            env.cr.execute("""  SELECT rp.name
                                     , SUM(l.amount_residual) AS residual
                                FROM account_move_line l
                                    LEFT JOIN account_account a ON (l.account_id=a.id)
                                    LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                                    LEFT JOIN res_partner rp ON l.partner_id = rp.id
                                WHERE 
                                CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                  AND l.reconciled IS FALSE
                                  AND l.invoice_id {}
                                  AND l.date_maturity < %s
                                GROUP BY rp.name
                                {}
                                LIMIT %s;
                                  """.format(data_filter, top_order), (expenses, date, limit,))
            lines = env.cr.dictfetchall()
        elif not expenses:
            env.cr.execute("""  SELECT rp.name
                                     , SUM(l.amount_residual) AS residual
                                FROM account_move_line l
                                    LEFT JOIN account_account a ON (l.account_id=a.id)
                                    LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                                    LEFT JOIN res_partner rp ON l.partner_id = rp.id
                                    LEFT JOIN account_invoice inv ON inv.id = l.invoice_id
                                WHERE
                                    CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                  AND l.reconciled IS FALSE
                                  AND l.invoice_id {}
                                  AND l.date_maturity < %s
                                  AND inv.user_id = %s
                                GROUP BY rp.name
                                {}
                                LIMIT %s;
                                  """.format(data_filter, top_order), (expenses, date, request.env.user.id, limit,))
            lines = env.cr.dictfetchall()
        else:
            lines = []
        #  Top not overdue
        for line in lines:
            top_overdue += f_round(line['residual'] * (-1.0 if expenses else 1.0))
            data_set.append({
                'company': line['name'],
                'sum': f_round(line['residual'] * (-1.0 if expenses else 1.0)),
                'overdue': True
            })
        if mode == 'manager':
            env.cr.execute("""  SELECT rp.name
                                     , SUM(l.amount_residual) AS residual
                                FROM account_move_line l
                                    LEFT JOIN account_account a ON (l.account_id=a.id)
                                    LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                                    LEFT JOIN res_partner rp ON l.partner_id = rp.id
                                WHERE
                                  CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                  AND l.reconciled IS FALSE
                                  AND l.invoice_id {}
                                GROUP BY rp.name
                                {}
                                LIMIT %s;
                              """.format(data_filter, top_order), (expenses, limit,))
            lines = env.cr.dictfetchall()
        elif not expenses:
            env.cr.execute("""  SELECT rp.name
                                     , SUM(l.amount_residual) AS residual
                                FROM account_move_line l
                                    LEFT JOIN account_account a ON (l.account_id=a.id)
                                    LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                                    LEFT JOIN res_partner rp ON l.partner_id = rp.id
                                    LEFT JOIN account_invoice inv ON inv.id = l.invoice_id
                                WHERE
                                CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                  AND l.reconciled IS FALSE
                                  AND l.invoice_id {}
                                  AND inv.user_id = %s
                                GROUP BY rp.name
                                {}
                                LIMIT %s;
                              """.format(data_filter, top_order), (expenses, request.env.user.id, limit,))
            lines = env.cr.dictfetchall()
        else:
            lines = []
        # Total not overdue
        for line in lines:
            top_all += f_round(line['residual'] * (-1.0 if expenses else 1.0))
            data_set.append({
                'company': line['name'],
                'sum': f_round(line['residual'] * (-1.0 if expenses else 1.0)),
                'all': True
            })
        if mode == 'manager':
            env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                   , COUNT(l.amount_residual) AS total_count
                              FROM account_move_line l
                              LEFT JOIN account_account a ON (l.account_id=a.id)
                              LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                              WHERE
                                  CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                AND l.reconciled IS FALSE
                                AND l.invoice_id {}
                                AND l.date_maturity >= %s
                          """.format(data_filter), (expenses, date))
            data = env.cr.fetchone()
        elif not expenses:
            env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                   , COUNT(l.amount_residual) AS total_count
                              FROM account_move_line l
                              LEFT JOIN account_account a ON (l.account_id=a.id)
                              LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                              LEFT JOIN account_invoice inv ON inv.id = l.invoice_id
                              WHERE
                              CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                AND l.reconciled IS FALSE
                                AND l.invoice_id {}
                                AND l.date_maturity >= %s
                                AND inv.user_id = %s
                          """.format(data_filter), (expenses, date, request.env.user.id,))
            data = env.cr.fetchone()
        else:
            data = []

        if data:
            total_not_overdue = f_round((data[0] or 0.0) * (-1.0 if expenses else 1.0))
            total_not_overdue_count = f_round(data[1] or 0.0)
        else:
            total_not_overdue = 0.0
            total_not_overdue_count = 0
        # Total overdue
        if mode == 'manager':
            env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                   , COUNT(l.amount_residual) AS total_count
                              FROM account_move_line l
                                LEFT JOIN account_account a ON l.account_id = a.id
                                LEFT JOIN account_account_type act ON a.user_type_id = act.id
                              WHERE
                                  CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                AND l.reconciled IS FALSE
                                AND l.invoice_id {}
                                AND l.date_maturity < %s
                           """.format(data_filter), (expenses, date))
            data = env.cr.fetchone()
        elif not expenses:
            env.cr.execute("""SELECT SUM(l.amount_residual) AS residual
                                   , COUNT(l.amount_residual) AS total_count
                              FROM account_move_line l
                                LEFT JOIN account_account a ON l.account_id = a.id
                                LEFT JOIN account_account_type act ON a.user_type_id = act.id
                                LEFT JOIN account_invoice inv ON inv.id = l.invoice_id
                              WHERE
                                  CASE WHEN %s THEN 
                                    act.type IN ('payable')
                                  ELSE
                                    act.type IN ('receivable')
                                  END
                                AND l.reconciled IS FALSE
                                AND l.invoice_id {}
                                AND l.date_maturity < %s
                                AND inv.user_id = %s
                           """.format(data_filter), (expenses, date, request.env.user.id,))
            data = env.cr.fetchone()
        else:
            data = []

        if data:
            total_overdue = f_round((data[0] or 0.0) * (-1.0 if expenses else 1.0))
            total_overdue_count = f_round(data[1] or 0.0)
        else:
            total_overdue = 0.0
            total_overdue_count = 0

        left_overdue = f_round((total_overdue or 0.0) - (top_overdue or 0.0))
        left_all = f_round((total_not_overdue or 0.0) + (total_overdue or 0.0) - (top_all or 0.0))

        if not tools.float_is_zero(left_overdue, precision_digits=2):
            data_set.append({
                'company': _('Kitos skolos'),
                'sum': left_overdue,
                'overdue': True,
                'bottom_line': True,
            })
        if not tools.float_is_zero(left_all, precision_digits=2):
            data_set.append({
                'company': _('Kitos skolos'),
                'sum': left_all,
                'all': True,
                'bottom_line': True,
            })
        return data_set, total_overdue_count, total_overdue_count + total_not_overdue_count

    def get_taxes(self, date=None):
        if not request.env.user.is_manager():
            return dumps(False)
        date_start = date['start'] if date \
            else (datetime.utcnow() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end = date['end'] if date \
            else (datetime.utcnow() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_start_dt = datetime.strptime(date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        vat_date = (date_start_dt + relativedelta(day=25)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        gpm_sodra_date = (date_start_dt + relativedelta(day=15)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        range_date_start = (date_start_dt + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        range_date_end = (date_end_dt + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        env = request.env
        AccountAccount = env['account.account']
        AccountMoveLine = env['account.move.line']
        company = env.user.sudo().company_id
        departments = env['hr.department'].sudo().search([])
        contracts = env['hr.contract'].sudo().search([
            ('date_start', '<=', range_date_end),
            '|',
            ('date_end', '>=', range_date_start),
            ('date_end', '=', False)
        ])
        taxes = []

        # VAT - split into reconciled/not reconciled
        vat_journal_id = company.vat_journal_id.id
        vat_account_id = company.vat_account_id.id
        vat_lines = AccountMoveLine.search([('move_id.state', '=', 'posted'), ('date', '>=', range_date_start),
                                            ('date', '<=', range_date_end), ('journal_id', '=', vat_journal_id),
                                            ('account_id', '=', vat_account_id)])
        if vat_lines:
            vat_residual = sum(x.amount_residual for x in vat_lines) * -1.0
            vat_total = sum(x.debit - x.credit for x in vat_lines) * -1.0

            if not tools.float_is_zero(vat_residual, precision_digits=2):
                taxes.append({
                    'date': vat_date,
                    'title': _('Value added tax (VAT)'),
                    'preliminary': False,
                    'amount': vat_residual,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': 'unpaid',
                    'category': 'VAT'
                })

            vat_paid = vat_total - vat_residual
            if not tools.float_is_zero(vat_paid, precision_digits=2):
                taxes.append({
                    'date': vat_date,
                    'title': _('Value added tax (VAT)'),
                    'preliminary': False,
                    'amount': vat_paid,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': 'paid',
                    'category': 'VAT'
                })
        else:
            # Only preliminary VAT amount can be found by summing account move lines
            preliminary_vat = self.get_vat(range_date_start, range_date_end)
            if not tools.float_is_zero(preliminary_vat, precision_digits=2):
                taxes.append({
                    'date': vat_date,
                    'title': _('Value added tax (VAT)'),
                    'preliminary': True,
                    'amount': -preliminary_vat,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': 'waiting_for_approval',
                    'category': 'VAT'
                })

        closed_payslip_run = env['hr.payslip.run'].search_count([
            ('date_end', '>=', range_date_start),
            ('date_start', '<=', range_date_end),
            ('state', '=', 'close'),
        ])
        is_preliminary = not closed_payslip_run
        tax_state = 'waiting_for_approval' if is_preliminary else 'unpaid'
        salary_journal_id = company.salary_journal_id.id
        # GPM - split into reconciled/not reconciled
        gpm_accounts = AccountAccount.search([('code', '=', '4487')], limit=1) | company.saskaita_gpm | \
                       departments.mapped('saskaita_gpm') | contracts.mapped('gpm_credit_account_id')
        gpm_lines = AccountMoveLine.search([('move_id.state', '=', 'posted'), ('date', '>=', range_date_start),
                                            ('date', '<=', range_date_end), ('account_id', 'in', gpm_accounts.ids),
                                            ('journal_id', '=', salary_journal_id)])
        if gpm_lines:
            gpm_residual = sum(x.amount_residual for x in gpm_lines) * -1.0
            gpm_total = sum(x.debit - x.credit for x in gpm_lines) * -1.0
            if not tools.float_is_zero(gpm_residual, precision_digits=2):
                taxes.append({
                    'date': gpm_sodra_date,
                    'title': _('Income tax amount (GPM)'),
                    'preliminary': is_preliminary,
                    'amount': gpm_residual,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': tax_state,
                    'category': 'GPM'
                })

            gpm_paid = gpm_total - gpm_residual
            if not tools.float_is_zero(gpm_paid, precision_digits=2):
                taxes.append({
                    'date': gpm_sodra_date,
                    'title': _('Income tax amount (GPM)'),
                    'preliminary': False,
                    'amount': gpm_paid,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': 'paid',
                    'category': 'GPM'
                })

        # SODRA - split into reconciled/not reconciled
        sodra_accounts = company.saskaita_sodra | departments.mapped('saskaita_sodra') | \
                         contracts.mapped('sodra_credit_account_id')
        sodra_lines = AccountMoveLine.search([('move_id.state', '=', 'posted'), ('date', '>=', range_date_start),
                                              ('date', '<=', range_date_end), ('account_id', 'in', sodra_accounts.ids),
                                              ('journal_id', '=', salary_journal_id)])
        if sodra_lines:
            sodra_residual = sum(x.amount_residual for x in sodra_lines) * -1.0
            sodra_total = sum(x.debit - x.credit for x in sodra_lines) * -1.0
            if not tools.float_is_zero(sodra_residual, precision_digits=2):
                taxes.append({
                    'date': gpm_sodra_date,
                    'title': _('Payable social security contributions (SoDra)'),
                    'preliminary': is_preliminary,
                    'amount': sodra_residual,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': tax_state,
                    'category': 'SODRA'
                })

            sodra_paid = sodra_total - sodra_residual
            if not tools.float_is_zero(sodra_paid, precision_digits=2):
                taxes.append({
                    'date': gpm_sodra_date,
                    'title': _('Payable social security contributions (SoDra)'),
                    'preliminary': False,
                    'amount': sodra_paid,
                    'currency_symbol': '€',
                    'currency_position': 'after',
                    'state': 'paid',
                    'category': 'SODRA'
                })

        return taxes

    def get_user_mode(self, user, expenses=False):
        """
        Gets the user mode based on the user groups
        :param user: res.users object
        :param expenses: indicates whether invoices-to-be-searched are of expense type
        :return: The mode of the user: user/manager/False
        """
        mode = False
        if user.has_group('robo_basic.group_robo_see_income'):
            mode = 'user'
        if user.is_manager() or \
                user.has_group('robo.group_menu_kita_analitika') or \
                user.has_group('robo_basic.robo_show_full_receivables_graph'):
            mode = 'manager'
        if expenses and user.has_group('robo.group_robo_see_all_expenses'):
            mode = 'manager'
        if user.sudo().show_only_personal_rp_amounts:
            mode = 'user'  # Force user mode if personal amounts is activated
        return mode

    def get_invoice_data(self, expenses=False):
        mode = self.get_user_mode(request.env.user, expenses=expenses)
        if not mode or mode not in ['user', 'manager']:
            return {}

        invoices, total_overdue_count, total_count = self.get_amounts(expenses=expenses, invoice_data=True, mode=mode)

        total_ex, total_count_ex = self.get_amounts(expenses=expenses, invoice_data=False, mode=mode)

        currency_symbol = self.get_currency_symbol()

        return {
            'invoices': invoices,
            'currency_symbol': currency_symbol,
            'total_overdue_count': total_overdue_count,
            'total_count': total_count,
            'total_ex': total_ex,
            'total_count_ex': total_count_ex,
            'mode': mode
        }

    @route('/pagalbininkas/get_graph_data', type='json', auth='user')
    def get_graph_data(self, chart_type, chart_filter, is_screen_big):
        allowed_charts = {}
        user = request.env.user
        if user.has_group('robo_basic.group_robo_see_income') or user.is_manager():
            allowed_charts.update({'stackedAreaChart': {'income'},
                                   'bulletChart': {'invoices'},
                                   'pieChart': {'expenses'}, })
        if user.is_manager():
            allowed_charts.setdefault('taxesTable', set()).update({'taxes'})
            allowed_charts.setdefault('stackedAreaChart', set()).update({'profit'})
            allowed_charts.setdefault('Cashflow', set()).update({'cashflow'})
        if user.is_premium_user():
            allowed_charts.setdefault('pieChart', set()).update({'expenses'})
        if user.has_group('robo_basic.group_view_income_compare_chart'):
            allowed_charts.setdefault('pieChart', set()).update({'incomeCompare'})
        if not (chart_type in allowed_charts and chart_filter['subtype'] in allowed_charts[chart_type]):
            return dumps(False)

        my_chart = {}
        d = {}

        # insert if available date and currency from request
        if chart_filter['dates']:
            d = {'date': chart_filter['dates']}

        # ****************************bulletChart****************************
        if chart_type == 'bulletChart':
            invoice_mode = chart_filter.get('invoice_mode')

            get_expenses = invoice_mode != 'default'
            all_invoice_data = self.get_invoice_data(expenses=get_expenses)

            mode = all_invoice_data.get('mode', {})
            invoice_data = all_invoice_data.get('invoices', [])
            currency_symbol = all_invoice_data.get('currency_symbol', '€')
            overdue_count = all_invoice_data.get('total_overdue_count', 0)
            total_count = all_invoice_data.get('total_count', 0)
            total_ex = all_invoice_data.get('total_ex', 0)
            total_count_ex = all_invoice_data.get('total_count_ex', 0)

            total_outstanding = sum(line['sum'] for line in invoice_data if line.get('all'))
            total_overdue = sum(line['sum'] for line in invoice_data if line.get('overdue'))

            aml_tooltip_header = _('Kitos mokėtinos sumos') if get_expenses else _('Kitos gautinos sumos')

            # We only show aml data to manager and non personal rp amounts mode
            show_aml_data = False
            if mode == 'manager' and not tools.float_is_zero(total_ex, precision_digits=2):
                show_aml_data = True

            # Build additional context
            additional_context = {'search_default_user_invoices': True if mode == 'user' else False}

            my_chart["bulletChart"] = {
                "chart_data": {
                    "ranges": [0, 0, total_outstanding],  # min, mean, max
                    "measures": [total_overdue],
                    "markers": [0],
                    "rangeLabels": ['', '', [_('Laukiantys mokėjimai'), "all", total_outstanding]],  # name + object
                    "measureLabels": [[_('Pradelsti mokėjimai'), "overdue", total_overdue]],
                },
                "info": {
                    "invoices": invoice_data,
                    "total_overdue": total_overdue,
                    "total_outstanding": total_outstanding,
                    "overdue_count": overdue_count,
                    "total_count": total_count,
                    "currency": currency_symbol,
                    "total_sum_ex": total_ex,
                    "total_count_ex": total_count_ex,
                    "aml_tooltip_header": aml_tooltip_header,
                    "show_aml_data": show_aml_data,
                    "additional_context": additional_context,
                },
            }
        if chart_type == 'taxesTable':
            my_chart['taxesTable'] = self.get_taxes(**d)

        # ****************************my_chart["pieChart"] ****************************
        if chart_type == 'pieChart' and chart_filter.get('subtype') == 'expenses':

            expense_mode = chart_filter.get('expense_mode')

            if expense_mode == 'default':
                expenses, currency_symbol = self.get_expenses(**d)

                total_expenses = sum(r['value'] for r in expenses)
                expenses = sorted(expenses, key=lambda r: r['value'], reverse=True)

                limit_number_expenses = 10 if is_screen_big else 5

                if len(expenses) > limit_number_expenses:
                    res = expenses[limit_number_expenses:]
                    spec_categories = filter(lambda r: r['id'] in ['DU', 'DEPR', 'Kita'], res)
                    if not spec_categories:
                        del expenses[limit_number_expenses:]
                        left_expenses = sum(r['value'] for r in expenses)
                        expenses.append({
                            'value': total_expenses - left_expenses,
                            'color': '#4dffd2',
                            'icon': 'icon-box',
                            'name': _('Likusios sugrupuotos sąskaitos'),
                            'id': [x['id'] for x in res]
                        })
                    else:
                        limit_number_expenses = limit_number_expenses - len(spec_categories)
                        res = expenses[limit_number_expenses:]
                        non_spec_categories = filter(lambda r: r['id'] not in ['DU', 'DEPR', 'Kita'], res)
                        del expenses[limit_number_expenses:]
                        expenses += spec_categories
                        left_expenses = sum(r['value'] for r in expenses)
                        expenses.append({
                            'value': total_expenses - left_expenses,
                            'color': '#4dffd2',
                            'icon': 'icon-box',
                            'name': _('Likusios sugrupuotos sąskaitos'),
                            'id': [x['id'] for x in non_spec_categories]
                        })

                my_chart["pieChart"] = {
                    "chart_data": expenses,
                    "info": {
                        "total": total_expenses,
                        "currency": currency_symbol
                    }
                }
            else:
                d.update({'expense_calc': True})
                if request.env.user.is_manager():
                    profit, currency_symbol = self.get_pelnas(**d)
                else:
                    profit = []
                    currency_symbol = self.get_currency_symbol()

                profit = sorted(profit, key=lambda r: r['date'])  # a bit faster solution with itemgetter?
                total_expenses = sum(line['exp'] for line in profit)

                for line in profit:
                    d = datetime.strptime(line['date'], "%Y-%m-%d")
                    line['date'] = int(mktime(d.timetuple())) * 1000

                my_chart['pieChart'] = {
                    "chart_data": [
                        {
                         "values": profit,
                         "color": CHART_POSITIVE_COLOR
                         },
                    ],
                    "info": {
                        "total": total_expenses,
                        "currency": currency_symbol
                    }
                }

        if chart_type == 'pieChart' and chart_filter.get('subtype') == 'incomeCompare':
            # This chart is only shown to member of special group
            if not request.env.user.has_group('robo_basic.group_view_income_compare_chart'):
                return dumps(False)

            incomes, currency_symbol = self.get_income_comparison(**d)
            total_income = sum(r['value'] for r in incomes)
            incomes.sort(key=lambda r: r['value'], reverse=True)

            limit_number = 10 if is_screen_big else 5

            if len(incomes) > limit_number:
                del incomes[limit_number:]
                left_incomes = sum(r['value'] for r in incomes)
                incomes.append({
                    'value': total_income - left_incomes,
                    'color': '#4dffd2',
                    'icon': 'icon-box',
                    'name': _('Kiti pardavėjai'),
                    'id': 'Other'
                })

            my_chart["pieChart"] = {
                "chart_data": incomes,
                "info": {
                    "total": total_income,
                    "currency": currency_symbol
                }
            }

        # ****************************stackedAreaChart****************************
        if chart_type == 'stackedAreaChart':
            if chart_filter['subtype'] == "income":
                key_name = "Pajamos"
                profit, currency_symbol = self.get_pajamos(**d)
            else:
                key_name = "Pelnas"
                profit, currency_symbol = self.get_pelnas(**d)

            # sort and make cumalative data
            profit = sorted(profit, key=lambda r: r['date'])  # a bit faster solution with itemgetter?

            total_income = sum(line['inc'] for line in profit)
            total_profit = sum(line['inc'] - line['exp'] for line in profit)

            for line in profit:
                d = datetime.strptime(line['date'], "%Y-%m-%d")
                line['date'] = int(mktime(d.timetuple())) * 1000

            my_chart['stackedAreaChart'] = {
                "chart_data": [
                    {"key": key_name,
                     "values": profit,
                     "color": CHART_POSITIVE_COLOR
                     },
                ],
                "info": {
                    "total_income": total_income,
                    "total_profit": total_profit,
                    "currency": currency_symbol
                }
            }
        # ****************************stackedAreaChart****************************
        if chart_type == 'Cashflow':
            key_name = "Pinigai"
            forecast_cash, accumulated_forecast, cashflow, end_cash, currency_symbol = self.get_cashflow(**d)

            if forecast_cash and not cashflow:
                cashflow = []
                for line in forecast_cash:
                    cashflow.append(line)
                total_forecast = sum(line['cashflow'] for line in forecast_cash)

                info = {
                    'forecast_total': total_forecast,
                    'forecast_balance': accumulated_forecast,
                    'currency': currency_symbol,
                }
            else:
                info = {
                    "end_cash": end_cash,
                    "currency": currency_symbol,
                }
            # sort and make cumalative data
            cashflow = sorted(cashflow, key=lambda r: r['date'])  # a bit faster solution with itemgetter?

            total_cashflow = sum(line['cashflow'] for line in cashflow)

            for line in cashflow:
                d = datetime.strptime(line['date'], "%Y-%m-%d")
                line['date'] = int(mktime(d.timetuple())) * 1000

            info['total_cashflow'] = total_cashflow
            my_chart['Cashflow'] = {
                "chart_data": [
                    {"key": key_name,
                     "values": cashflow,
                     "color": CHART_POSITIVE_COLOR
                     },
                ],
                "info": info,
            }

        return dumps(my_chart[chart_type])

    @route("/graph/cashflow/last_statement_closed_date", type='json', auth='user')
    def get_bank_statement_last_date(self):
        if request.env.user.is_manager():
            company = request.env.user.sudo().company_id
            request.env.cr.execute(self.get_bank_end_balance_query())
            data = request.env.cr.dictfetchall()
            if data and data[0]:
                dates = []
                popup_data = []
                for x in data:
                    # TODO: Still have to browse the journal obj, because name field in DB has some random value
                    journal = request.env['account.journal'].browse(x['journal_id'])

                    # Get bank update values
                    update_date = x.get('update_date')
                    end_balance = x.get('end_bal') if x.get('end_bal') is not None else '-'
                    end_balance_comp_curr = x.get('end_bal_curr') if x.get('end_bal_curr') is not None else '-'

                    # Compose balance display string
                    if journal.currency_id:
                        balance_real = '{} {} / {} {}'.format(
                            end_balance_comp_curr, company.currency_id.name,  end_balance, journal.currency_id.name)
                    else:
                        balance_real = '{} {}'.format(end_balance, company.currency_id.name)

                    dates.append(update_date)
                    popup_data.append({'account_name': journal.name, 'date': update_date, 'balance_real': balance_real})
                display_date = {'date': min(dates)}
                data_dict = {
                    'display_date': display_date,
                    'popup_data': popup_data
                }
                return dumps(data_dict)

        return dumps('')

    @route('/graph/get_default_dates', type='json', auth='user')
    def get_graph_default_dates(self):
        start_date = request.env.user.sudo().company_id.compute_fiscalyear_dates()['date_from']
        dates = {
            "start": datetime.utcnow().replace(year=start_date.year, month=start_date.month, day=start_date.day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            "end": datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        }
        return dumps(dates)

    @route('/graph/get_default_comparison_dates', type='json', auth='user')
    def get_grapt_comparison_default_dates(self):
        dates = {
            "start": datetime.utcnow().replace(day=1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            "end": datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        }
        return dumps(dates)
