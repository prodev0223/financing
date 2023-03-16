# -*- coding: utf-8 -*-

from odoo import fields, models, _, api, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class AccReportGeneralLedgerSL(models.TransientModel):

    _name = "debt.act.wizard"
    _description = 'Debt Coordination'

    def _partner_ids(self):
        if self._context.get('partner_ids', False):
            partner_ids = self._context.get('partner_ids', False)
            return [(6, 0, partner_ids)]
            # partners = self.env['account.invoice'].browse(partner_ids)

    def _account_ids(self):
        if self._context.get('account_ids', False):
            account_ids = self._context.get('account_ids', False)
            return [(6, 0, account_ids)]

    def default_date_from(self):
        fiscalyear_date_from = self.env.user.company_id.compute_fiscalyear_dates()['date_from']
        years = -1 if datetime.utcnow() < (fiscalyear_date_from + relativedelta(months=4)) else 0
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from'] + relativedelta(years=years)

    def default_date_to(self):
        fiscalyear_date_from = self.env.user.company_id.compute_fiscalyear_dates()['date_from']
        years = -1 if datetime.utcnow() < (fiscalyear_date_from + relativedelta(months=4)) else 0
        return self.env.user.company_id.compute_fiscalyear_dates()['date_to'] + relativedelta(years=years)

    all_partners = fields.Boolean(string='Visi partneriai', default=False)
    date = fields.Date(string='Data', default=fields.Date.today)
    partner_ids = fields.Many2many('res.partner', lt_string='Partneris', string='Partneris', default=_partner_ids)
    account_type_filter = fields.Selection([('all', 'Visos sumos'),
                                            ('receivable', 'Gautinos sumos'),
                                            ('payable', 'Mokėtinos sumos'),
                                            ('payable_receivable', 'Gautinos ir mokėtinos sumos')],
                                           string='Sąskaitų tipai', default='payable_receivable', required=True)
    account_ids = fields.Many2many('account.account', string='Buhalterinės sąskaitos', default=_account_ids,
                                   groups="skolu_suderinimas.group_select_account_in_debt_act,"
                                          "robo.group_select_account_in_account_aged_trial_balance")
    type = fields.Selection([('unreconciled', 'Neapmokėtos skolos'), ('all', 'Apyvarta')], string='Tipas', default='unreconciled', required=True)
    date_from = fields.Date(string='Data nuo', default=default_date_from, required=True)
    date_to = fields.Date(string='Data iki', default=default_date_to, required=True)
    detail_level = fields.Selection([('detail', 'Detalu'), ('sum', 'Tik sumos')], string='Detalumas', default='detail', required=True)
    show_original_amounts = fields.Boolean(string='Grupuoti pagal originalias valiutas',
                                           help='Ataskaita išgrupuojama pagal originalias mokėjimų sumas/valiutas. '
                                                'Naudinga, kai yra sąskaitų, apmokėtų kita valiuta')
    show_accounts = fields.Boolean(string='Rodyti buhalterinę sąskaitą')
    print_only_debt_amounts = fields.Boolean(string="Spausdinti tik skolos likučius", default=False)
    dont_show_zero_values = fields.Boolean(string="Nerodyti nulinių įrašų", default=True)
    dont_show_zero_debts = fields.Boolean(string="Nerodyti įrašų be skolų", default=True)

    @api.onchange('account_type_filter')
    def _onchange_account_type_filter(self):
        """
        Add a domain in selectable accounts based on account_type_filter type
        :return: field domain (dict)
        """
        if self.account_type_filter == 'payable_receivable':
            return {'domain': {'account_ids': [('user_type_id.type', 'in', ['payable', 'receivable'])]}}
        elif self.account_type_filter == 'receivable':
            return {'domain': {'account_ids': [('user_type_id.type', '=', 'receivable')]}}
        elif self.account_type_filter == 'payable':
            return {'domain': {'account_ids': [('user_type_id.type', '=', 'payable')]}}
        else:
            return {'domain': {'account_ids': []}}

    @api.multi
    def get_data(self):
        """ Get data used for the report calculation as a dictionary """
        if self.all_partners:
            query = """
                SELECT
                    DISTINCT(aml.partner_id) 
                FROM
                    account_move_line aml
                INNER JOIN
                    account_move am
                        ON am.id = aml.move_id
                WHERE
                    aml.partner_id IS NOT NULL
                    AND am.state = 'posted'
                    AND aml.date <= %s"""
            params = [self.date_to if self.type == 'all' else self.date]
            if self.type == 'all':
                query += """
                    AND aml.date >= %s"""
                params.append(self.date_from)
            if (self.env.user.is_accountant() or self.env.user.has_group(
                    'robo.group_select_account_in_account_aged_trial_balance')) and self.account_ids:
                query += """
                    AND aml.account_id IN %s"""
                params.append(tuple(self.account_ids.ids))
            else:
                account_ids = self.env['report.debt.reconciliation.base'].get_default_payable_receivable(self.account_type_filter)
                query += """
                    AND aml.account_id IN %s"""
                params.append(tuple(account_ids))
            self.env.cr.execute(query, tuple(params))
            partners = self.env['res.partner'].search([('id', 'in', [row[0] for row in self.env.cr.fetchall()])])
        else:
            partners = self.partner_ids
        if self._context.get('limited'):
            partners = partners.filtered(lambda r: not r.employee_ids)
        return {'date': self.date,
                'partner_ids': partners.ids,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'type': self.type,
                'detail_level': self.detail_level,
                'account_type_filter': self.account_type_filter,
                'account_ids': self.account_ids.ids
                if self.env.user.has_group('skolu_suderinimas.group_select_account_in_debt_act') or
                   self.env.user.has_group('robo.group_select_account_in_account_aged_trial_balance') else None,
                'show_original_amounts': self.show_original_amounts,
                'show_accounts': self.show_accounts,
                'payment_reminder': False,
                'dont_show_zero_values': self.dont_show_zero_values,
                'dont_show_zero_debts': self.dont_show_zero_debts,
                'force_lang': self._context.get('lang') or self.env.user.lang or 'lt_LT',
                }

    @api.multi
    def generate_debt_act(self):
        if not self.env.user.has_group('robo_basic.group_robo_premium_manager'):
            raise exceptions.UserError(_('Tik vadovas gali matyti šią ataskaitą'))
        data = self.get_data()
        return self.env['report'].get_action(self, 'skolu_suderinimas.report_aktas_multi', data=data)

    @api.multi
    def generate_minimal_debt_act(self):
        if not self.env.user.has_group('robo_basic.group_robo_premium_manager'):
            raise exceptions.UserError(_('Tik vadovas gali matyti šią ataskaitą'))
        data = self.get_data()
        return self.env['report'].get_action(self, 'skolu_suderinimas.report_aktas_multi_minimal', data=data)

    @api.multi
    def xls_export(self):
        if not self.env.user.has_group('robo_basic.group_robo_premium_manager'):
            raise exceptions.UserError(_('Tik vadovas gali matyti šią ataskaitą'))
        data = self.get_data()
        return self.export_excel(data)

    @api.multi
    def action_dynamic_view(self):
        self.ensure_one()
        wizard = self._create_debt_act_wizard()
        return wizard.action_view()


AccReportGeneralLedgerSL()
