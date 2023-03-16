# -*- coding: utf-8 -*-
from __future__ import division
from odoo import _, api, exceptions, fields, models, tools


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    _default_field_sequence = 100  # by default do not show any field in filter and group by sections.

    code = fields.Char(required=True)
    balance = fields.Monetary(
        compute='_compute_debit_credit_balance',
        groups="robo_analytic.group_robo_analytic_see_amounts,robo_basic.group_robo_premium_manager", store=True)
    debit = fields.Monetary(
        compute='_compute_debit_credit_balance',
        groups="robo_analytic.group_robo_analytic_see_amounts,robo_basic.group_robo_premium_manager", store=True)
    credit = fields.Monetary(
        compute='_compute_debit_credit_balance',
        groups="robo_analytic.group_robo_analytic_see_amounts,robo_basic.group_robo_premium_manager", store=True)
    partner_id = fields.Many2one(sequence=50)
    project_manager = fields.Many2one('res.users', sequence=50, string='Projektų vadovas')
    create_date = fields.Datetime(sequence=50)
    privacy_visibility = fields.Selection([
        ('followers', 'Komandos nariams'),
        ('employees', 'Matoma visiems darbuotojams'),
    ],
        string='Privatumas', lt_string='Privatumas', required=False, default='followers', help="",
        groups='robo_basic.group_robo_free_manager,robo_basic.group_robo_premium_manager,analytic.group_analytic_accounting')
    team_involvement_ids = fields.One2many(
        'project.involvement', 'analytic_account_id', readonly=False,
        string='Team involvement', inverse='_set_team_followers_inverse',
        groups='robo_basic.group_robo_free_manager,robo_basic.group_robo_premium_manager,analytic.group_analytic_accounting')
    account_type = fields.Selection([
        ('income', 'Pajamų centras'),
        ('expense', 'Kaštų centras'),
        ('profit', 'Pelno centras'),
    ], string='Analitinės sąskaitos tipas', default='profit', required=True)
    analytic_account_budget_line_ids = fields.One2many('analytic.account.budget.line',
                                                       'account_analytic_id', string='Biudžeto eilutės')
    expense_percentage = fields.Char(
        compute='compute_budget_percentages', string='Planuotos išlaidos',
        groups="robo_analytic.group_robo_analytic_see_amounts,robo_basic.group_robo_premium_manager")
    income_percentage = fields.Char(
        compute='compute_budget_percentages', string='Planuotos pajamos',
        groups="robo_analytic.group_robo_analytic_see_amounts,robo_basic.group_robo_premium_manager")
    analytic_group_id = fields.Many2one('account.analytic.group', string='Analytic group')

    @api.multi
    def open_budget_lines(self):
        self.ensure_one()
        action = self.env.ref('robo_analytic.open_account_analytic_budget_line_tree').read()[0]
        domain = [('account_analytic_id', '=', self.id)]
        if self._context.get('from_date', False) and self._context.get('to_date', False):
            domain.extend(['|', '&', ('date_to', '>=', self._context['from_date']),
                           ('date_to', '<=', self._context['to_date']),
                           '&',
                           ('date_from', '<=', self._context['to_date']),
                           ('date_from', '>=', self._context['from_date']),
                           ])
        action['domain'] = domain
        ctx = self._context.copy()
        ctx.update({'parent_id': self.id})
        action['context'] = ctx
        return action

    @api.one
    @api.depends('analytic_account_budget_line_ids.expense_budget', 'debit', 'credit')
    def compute_budget_percentages(self):
        if self.analytic_account_budget_line_ids:
            domain = [('id', 'in', self.analytic_account_budget_line_ids.ids)]
            if self._context.get('from_date', False) and self._context.get('to_date', False):
                domain.extend(['|', '&', ('date_to', '>=', self._context['from_date']),
                               ('date_to', '<=', self._context['to_date']),
                               '&',
                               ('date_from', '<=', self._context['to_date']),
                               ('date_from', '>=', self._context['from_date']),
                               ])

            records = self.env['analytic.account.budget.line'].search(domain)
            expense_budget = sum(x.expense_budget for x in records)
            income_budget = sum(x.income_budget for x in records)
            if expense_budget:
                # P3:DivOK
                e_percentage = tools.float_round(self.debit / expense_budget * 100, precision_digits=2)
                self.expense_percentage = '{} / {} %'.format(expense_budget, e_percentage)
            else:
                self.expense_percentage = '{} / {} %'.format(expense_budget, 100)
            if income_budget:
                # P3:DivOK
                i_percentage = tools.float_round(self.credit / income_budget * 100, precision_digits=2)
                self.income_percentage = '{} / {} %'.format(income_budget, i_percentage)
            else:
                self.income_percentage = '{} / {} %'.format(income_budget, 100)

    @api.multi
    def _compute_debit_credit_balance(self):
        if not self:
            return
        AnalyticLine = self.env['account.analytic.line']
        account_ids = self.mapped('id')
        data_debit = {account_id: 0.0 for account_id in account_ids}
        data_credit = {account_id: 0.0 for account_id in account_ids}
        acc_ids = tuple(self.mapped('id'))

        query = '''SELECT
                            account_analytic_account.id, sum(account_analytic_line.amount)
                        FROM account_analytic_line
                            LEFT JOIN account_move_line on account_analytic_line.move_id = account_move_line.id
                            LEFT JOIN account_account on account_analytic_line.general_account_id = account_account.id
                            LEFT JOIN account_analytic_account on account_analytic_line.account_id = account_analytic_account.id
                        WHERE account_account.code like %s and account_analytic_account.id in %s
                        '''

        date_args = ()
        if self._context.get('from_date'):
            query += ''' and account_analytic_line.date >= %s'''
            date_args += (self._context.get('from_date'),)
        if self._context.get('to_date'):
            query += ''' and account_analytic_line.date <= %s'''
            date_args += (self._context.get('to_date'),)
        query += '''GROUP BY account_analytic_account.id'''

        # Get income amounts
        args_credit = ('5%', acc_ids,) + date_args if date_args else ('5%', acc_ids,)
        self.env.cr.execute(query + ';', args_credit)
        credit = self.env.cr.fetchall()

        for line in credit:
            data_credit[line[0]] = line[1]

        # Get expense amounts
        args_debit = ('6%', acc_ids,) + date_args if date_args else ('6%', acc_ids,)
        self.env.cr.execute(query + ';', args_debit)
        debit = self.env.cr.fetchall()

        for line in debit:
            data_debit[line[0]] = line[1]

        # Loop through amounts without related general ledger account
        domain = [('account_id', 'in', account_ids), ('general_account_id', '=', False)]
        account_amounts = AnalyticLine.search_read(domain, ['account_id', 'amount'])
        for account_amount in account_amounts:
            if account_amount['amount'] < 0.0:
                data_debit[account_amount['account_id'][0]] += account_amount['amount']
            else:
                data_credit[account_amount['account_id'][0]] += account_amount['amount']

        for account in self:
            account.debit = abs(data_debit.get(account.id, 0.0))
            account.credit = data_credit.get(account.id, 0.0)
            account.balance = account.credit - account.debit

    @api.one
    def _set_team_followers_inverse(self):
        p_ids = []
        for project_inv in self.team_involvement_ids:
            if not project_inv.id:  # only new member will be added as follower
                if project_inv.user_id:
                    p_ids.append(project_inv.user_id.partner_id.id)
        subtypes_id = self.env['mail.message.subtype'].search(['|', '&', ('default', '=', True),
                                                               ('res_model', '=', False),
                                                               '&',
                                                               ('name', 'in', ['Task Opened', 'Project Stage Changed']),
                                                               ('res_model', '=', 'account.analytic.account')
                                                               ]).mapped('id')
        self.message_subscribe(partner_ids=p_ids, subtype_ids=subtypes_id)

    @api.multi
    @api.constrains('code')
    def code_constraint(self):
        for rec in self:
            if len(rec.code) > 20:
                raise exceptions.ValidationError(_('Kodas negali būti ilgesnis nei 20 simbolių.'))
            if rec.code and ' ' in rec.code:
                raise exceptions.ValidationError(_('Kode negali būti tarpų.'))

    @api.onchange('code')
    def onchange_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name and operator in ['like', '=like', 'ilike', '=ilike']:
            recs = self.search([('code', '=like', name.lower() + "%")] + args,
                               limit=limit)
            add = self.search([('code', '=like', name.upper() + "%")] + args,
                              limit=limit)
            recs |= add
            #FIXME: do we want to not include accounts where the name is also part of some other account code?
            if not recs:
                recs = self.search([('name', operator, name)] + args,
                                   limit=limit)
        elif name and operator == '=':
            domain = [('code', operator, name)] + args
            recs = self.search(['|', ('name', '=', name), ('code', '=', name)] + domain, limit=limit)
        elif name and operator and (operator.startswith('!') or operator.startswith('not')):
            recs = self.search([('name', operator, name), ('code', operator, name)] + args, limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.model
    def create(self, vals):
        if 'code' in vals:
            vals['code'] = vals['code'].upper()
        else:
            vals['code'] = ' '
        res = super(AccountAnalyticAccount, self).create(vals)
        return res

    @api.constrains('code')
    def _code_unique(self):
        for rec in self:
            if self.sudo().env['account.analytic.account'].search_count([('code', '=', rec.code)]) >= 2:
                raise exceptions.ValidationError(_('Kodas turi būti unikalus'))

    @api.model
    def action_open_analytic_account_tree(self):
        """
        Action to open analytic account tree after recomputing debit/credit/balance
        :return: Dictionary to open analytic account tree
        """
        # Only recompute debit/credit/balance when opening the report
        self.env['account.analytic.account'].search([]).sudo()._compute_debit_credit_balance()
        return {
            'name': _('Analytic accounts'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.analytic.account',
            'view_id': False,
            'type': 'ir.actions.act_window',
        }