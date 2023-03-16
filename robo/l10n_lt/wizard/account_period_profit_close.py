# -*- encoding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, _, api, exceptions, tools


class AccountPeriodProfitClose(models.TransientModel):

    _name = 'account.period.profit.close'

    def default_date_from(self):
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from'] + relativedelta(years=-1)

    def default_date_to(self):
        return self.env.user.company_id.compute_fiscalyear_dates()['date_to'] + relativedelta(years=-1)

    def default_journal_id(self):
        return self.env.user.company_id.period_close_journal_id

    def default_account_id(self):
        return self.env['account.account'].search([('company_id', '=', self.env.user.company_id.id), ('code', '=', '390')], limit=1)

    company_id = fields.Many2one('res.company', string='Kompanija', requied=True, default=lambda self: self.env.user.company_id)
    date_from = fields.Date(string='Data nuo', required=True, default=default_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=default_date_to)
    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True, default=default_journal_id)
    account_id = fields.Many2one('account.account', string='Sąskaita į kurią perkelti', required=True, default=default_account_id)
    income_amount = fields.Float(string='Pajamos per periodą', compute='_compute_income_profit_tax')
    profit_amount = fields.Float(string='Pelnas per periodą', compute='_compute_income_profit_tax')
    employee_count = fields.Float(string='Vidutinis darbuotojų skaičius per periodą', compute='_compute_employee_count')
    profit_tax_percent = fields.Float(string='Pelno mokesčio procentas', compute='_compute_income_profit_tax')
    profit_tax = fields.Float(string='Pelno mokestis', compute='_compute_income_profit_tax')
    move_profit = fields.Boolean(string='Perkelti pelną (nuostolį)', default=True)
    calculate_profit_tax = fields.Boolean(string='Skaičiuoti pelno mokestį', default=True)

    @api.one
    @api.depends('date_from', 'date_to', 'calculate_profit_tax')
    def _compute_income_profit_tax(self):
        """ Compute profit amount by summing account move lines of 5th and 6th class
        Profit tax is computed using formula profit_amount * profit_tax_percent
        Profit tax percent is always 15% if average employee count is more than 10
        or income amount is at least 300 000 """

        if not self.calculate_profit_tax:
            return

        no_deduction_acc_codes = ('62034', '63043', '651', '652')
        no_tax_calc_acc_codes = ('631208', '631204')

        # Check if there are account move lines of financial aid
        self._cr.execute('''
        SELECT count(*) 
            FROM account_move_line aml
                JOIN account_move am ON aml.move_id = am.id 
                JOIN account_account ON aml.account_id = account_account.id
            WHERE aml.date >= %s 
                AND aml.date <= %s
                AND am.state = 'posted'
                AND account_account.code in %s''', (self.date_from, self.date_to, no_tax_calc_acc_codes))
        financial_aid = self._cr.fetchall()
        if financial_aid and financial_aid[0] and financial_aid[0][0]:
            raise exceptions.UserError(_('Pelno mokestis turi būti skaičiuojamas rankiniu būdu - įmonė turi paramos sąnaudų.'))

        # Sum the balance of amounts in 5th and 6th class
        self._cr.execute('''
SELECT sum(aml.balance)
     FROM account_move_line aml
         JOIN account_move am on aml.move_id = am.id 
         JOIN account_account ON aml.account_id = account_account.id
     WHERE aml.date >= %s 
        AND aml.date <= %s
        AND am.state = 'posted'
        AND (account_account.code like '5%%' or account_account.code like '6%%')''', (self.date_from, self.date_to))

        profit = self.env.cr.fetchone()[0] or 0.0

        # Sum the balance of amounts in 5th class
        self._cr.execute('''
        SELECT sum(aml.balance)
             FROM account_move_line aml
                 JOIN account_move am on aml.move_id = am.id 
                 JOIN account_account ON aml.account_id = account_account.id
             WHERE aml.date >= %s 
                AND aml.date <= %s
                AND am.state = 'posted'
                AND (account_account.code like '5%%')''', (self.date_from, self.date_to))

        income = self.env.cr.fetchone()[0] or 0.0

        # Sum the balance of non-deductible amounts
        self._cr.execute('''
        SELECT sum(aml.balance)
             FROM account_move_line aml
                 JOIN account_move am on aml.move_id = am.id 
                 JOIN account_account ON aml.account_id = account_account.id
             WHERE aml.date >= %s 
                AND aml.date <= %s
                AND am.state = 'posted'
                AND account_account.code in %s''', (self.date_from, self.date_to, no_deduction_acc_codes))

        non_deducted = self.env.cr.fetchone()[0] or 0.0

        self.income_amount = income * -1
        self.profit_amount = profit * -1 + non_deducted
        self.profit_tax_percent = 15 if self.employee_count > 10 or self.income_amount >= 300000 else 0
        if self.profit_amount > 0.0:
            # P3:DivOK - profit amount is float
            self.profit_tax = self.profit_tax_percent * self.profit_amount / 100

    @api.one
    @api.depends('date_from')
    def _compute_employee_count(self):
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        fiscal_date_from = self.env.user.company_id.compute_fiscalyear_dates(date=date_from)['date_from']
        employee_count_report = self.env['employee.count.report'].create({
            'date_from': fiscal_date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT), #TODO: Or should it be calendar year, always?
        })
        self.employee_count = employee_count_report.employee_count

    @api.multi
    def close_period_profit(self):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Tik buhalteris gali atlikti šią operaciją'))
        # create move
        self._cr.execute('''
SELECT count(*) 
    FROM account_move_line aml
        JOIN account_move am ON aml.move_id = am.id 
        JOIN account_account ON aml.account_id = account_account.id
    WHERE state != 'posted' 
        AND am.date >= %s 
        AND am.date <= %s
        AND (account_account.code like '5%%' or account_account.code like '6%%')''', (self.date_from, self.date_to))
        non_posted = self._cr.fetchall()
        if non_posted and non_posted[0] and non_posted[0][0]:
            raise exceptions.UserError(_('Yra nepatvirtintų įrašų'))
        profit_tax = self.profit_tax
        self._cr.execute('''
SELECT aml.account_id, sum(aml.balance) balance
     FROM account_move_line aml
         JOIN account_move am on aml.move_id = am.id 
         JOIN account_account ON aml.account_id = account_account.id
     WHERE aml.date >= %s 
        AND aml.date <= %s
        AND am.state = 'posted'
        AND (account_account.code like '5%%' or account_account.code like '6%%')
     GROUP BY account_id''', (self.date_from, self.date_to))
        sums = self._cr.dictfetchall()
        am_lines = []
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        total_balance = 0.0
        fiscal_year_dates = self.env.user.company_id.compute_fiscalyear_dates()
        if date_from_dt.month == fiscal_year_dates['date_from'].month and \
                date_from_dt.day == fiscal_year_dates['date_from'].day and \
                date_to_dt.month == fiscal_year_dates['date_to'].month and \
                date_to_dt.day == fiscal_year_dates['date_to'].day:
            ref = _('Pelno uždarymas %s m.') % date_from_dt.year
            year_close = True
        else:
            ref = _('Pelno uždarymas %s - %s') % (self.date_from, self.date_to)
            year_close = False
        for row in sums:
            balance = row['balance']
            total_balance += balance
            if balance and tools.float_compare(balance, 0, precision_digits=2) != 0:
                aml_vals = {'name': '/',
                            'account_id': row['account_id'],
                            'credit': balance if balance > 0 else 0,
                            'debit': 0 if balance > 0 else -balance}
                am_lines.append((0, 0, aml_vals))
        dest_line_vals = {'name': '/',
                          'account_id': self.account_id.id,
                          'credit': 0 if total_balance > 0 else - total_balance,
                          'debit': total_balance if total_balance > 0 else 0}
        am_lines.append((0, 0, dest_line_vals))
        am_vals = {'journal_id': self.journal_id.id,
                   'date': self.date_to,
                   'ref': ref,
                   'line_ids': am_lines}
        move = self.env['account.move'].create(am_vals)
        move.with_context(skip_analytics=True).post()
        action = self.env.ref('account.action_move_journal_line').read()[0]
        action['domain'] = [('id', 'in', [move.id])]
        if year_close:
            Account = self.env['account.account']
            journal = self.env['account.journal'].search([('code', '=', 'KITA')], limit=1)
            if self.move_profit:
                # 1st step: move balance to account 3411 for date XXXX-12-31
                account_from = self.account_id
                account_to = Account.search([('code', '=', '3411')], limit=1)
                move_name = _('%s uždarymas') % account_from.code
                self._cr.execute('''
                SELECT sum(aml.balance)
                     FROM account_move_line aml
                         JOIN account_move am on aml.move_id = am.id
                         JOIN account_account ON aml.account_id = account_account.id
                     WHERE aml.date >= %s
                        AND aml.date <= %s
                        AND am.state = 'posted'
                        AND account_account.code = %s''', (self.date_from, self.date_to, account_from.code))
                balance = self.env.cr.fetchone()[0] or 0.0
                if balance and tools.float_compare(balance, 0, precision_digits=2) != 0:
                    am_lines = []
                    src_aml_vals = {'name': move_name,
                                    'account_id': account_from.id,
                                    'credit': balance if balance > 0 else 0,
                                    'debit': 0 if balance > 0 else -balance}
                    am_lines.append((0, 0, src_aml_vals))

                    dest_line_vals = {'name': move_name,
                                      'account_id': account_to.id,
                                      'credit': 0 if balance > 0 else -balance,
                                      'debit': balance if balance > 0 else 0}
                    am_lines.append((0, 0, dest_line_vals))

                    am_vals = {'journal_id': journal.id,
                               'date': self.date_to,
                               'ref': move_name,
                               'line_ids': am_lines}
                    move = self.env['account.move'].create(am_vals)
                    move.with_context(skip_analytics=True).post()

                # 2nd step: move balance from account 3411 to account 3421 for date YYYY-01-01
                account_from = account_to
                account_to = Account.search([('code', '=', '3421')], limit=1)
                move_name = _('%s m. pelnas') % date_from_dt.year
                move_date = (date_to_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                self._cr.execute('''
                SELECT sum(aml.balance)
                     FROM account_move_line aml
                         JOIN account_move am on aml.move_id = am.id
                         JOIN account_account ON aml.account_id = account_account.id
                     WHERE aml.date >= %s
                        AND aml.date <= %s
                        AND am.state = 'posted'
                        AND account_account.code = %s''', (self.date_from, self.date_to, account_from.code))
                balance = self.env.cr.fetchone()[0] or 0.0
                if balance and tools.float_compare(balance, 0, precision_digits=2) != 0:
                    am_lines = []
                    src_aml_vals = {'name': move_name,
                                    'date_maturity': self.date_to,
                                    'account_id': account_from.id,
                                    'credit': balance if balance > 0 else 0,
                                    'debit': 0 if balance > 0 else -balance}
                    am_lines.append((0, 0, src_aml_vals))

                    dest_line_vals = {'name': move_name,
                                      'date_maturity': self.date_to,
                                      'account_id': account_to.id,
                                      'credit': 0 if balance > 0 else -balance,
                                      'debit': balance if balance > 0 else 0}
                    am_lines.append((0, 0, dest_line_vals))

                    am_vals = {'journal_id': journal.id,
                               'date': move_date,
                               'ref': move_name,
                               'line_ids': am_lines}
                    move = self.env['account.move'].create(am_vals)
                    move.with_context(skip_analytics=True).post()

            if self.calculate_profit_tax:
                # 3rd step: create a move for profit tax
                account_from = Account.search([('code', '=', '4470')], limit=1)
                account_to = Account.search([('code', '=', '6900')], limit=1)
                move_name = _('%s m. pelno mokestis') % date_from_dt.year
                if tools.float_compare(profit_tax, 0, precision_digits=2) > 0:
                    am_lines = []
                    src_aml_vals = {'name': move_name,
                                    'account_id': account_from.id,
                                    'credit': profit_tax,
                                    'debit': 0}
                    am_lines.append((0, 0, src_aml_vals))

                    dest_line_vals = {'name': move_name,
                                      'account_id': account_to.id,
                                      'credit': 0,
                                      'debit': profit_tax}
                    am_lines.append((0, 0, dest_line_vals))

                    am_vals = {'journal_id': journal.id,
                               'date': self.date_to,
                               'ref': move_name,
                               'line_ids': am_lines}
                    move = self.env['account.move'].create(am_vals)
                    move.with_context(skip_analytics=True).post()

        # change fiscal year close date
        self.env.user.sudo().company_id.write({
            'fiscalyear_lock_date': self.date_to
        })
        return action


AccountPeriodProfitClose()
