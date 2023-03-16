# -*- coding: utf-8 -*-

from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountAgedTrialBalance(models.TransientModel):
    _inherit = 'account.aged.trial.balance'

    def default_date_from(self):
        get_last_year_dates = self.env.context.get('get_last_year_dates')
        fiscalyear_date_from = self.env.user.company_id.compute_fiscalyear_dates()['date_from']
        years = 0
        if datetime.utcnow() < (fiscalyear_date_from + relativedelta(months=4)) or get_last_year_dates:
            years = -1
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from'] + relativedelta(years=years)

    def default_date_to(self):
        get_last_year_dates = self.env.context.get('get_last_year_dates')
        fiscalyear_date_from = self.env.user.company_id.compute_fiscalyear_dates()['date_from']
        years = 0
        if datetime.utcnow() < (fiscalyear_date_from + relativedelta(months=4)) or get_last_year_dates:
            years = -1
        return self.env.user.company_id.compute_fiscalyear_dates()['date_to'] + relativedelta(years=years)

    filtered_partner_ids = fields.Many2many('res.partner', string='Filtruoti partnerius')
    display_partner = fields.Selection(
        [('all', 'Visus'), ('filter', 'Filtruoti partnerius')],
        string='Rodyti partnerius', required=True, default='all')
    invoices_only = fields.Boolean(string='Rodyti tik sąskaitas faktūras')
    include_proforma = fields.Boolean(string='Įtraukti išankstines sąskaitas')
    only_reduced = fields.Boolean(compute='_compute_only_reduced')
    account_ids = fields.Many2many('account.account', string='Sąskaitos',
                                   help='Jeigu nustatysite sąskaitas šiame laukelyje, '
                                        'sąskaitų tipo pasirinkimo laukelis bus ignoruojamas')
    short_report = fields.Boolean(string='Sutrumpinta ataskaita (Bankui)')
    report_type = fields.Selection(
        [('debt_act', 'Skolų likučių ataskaita'), ('aged_balance', 'Skolų vėlavimo ataskaita')],
        string='Ataskaitos tipas', required=True, default='aged_balance')

    # Debt act report fields to pass to wizard
    date = fields.Date(string='Data', default=fields.Date.today)
    type = fields.Selection([('unreconciled', 'Neapmokėtos skolos'), ('all', 'Apyvarta')], string='Tipas', default='unreconciled', required=True)
    date_from_debt = fields.Date(string='Data nuo', default=default_date_from, required=True)
    date_to = fields.Date(string='Data iki', default=default_date_to, required=True)
    detail_level = fields.Selection([('detail', 'Detalu'), ('sum', 'Tik sumos')], string='Detalumas', default='detail', required=True)
    show_original_amounts = fields.Boolean(string='Grupuoti pagal originalias valiutas',
                                           help='Ataskaita išgrupuojama pagal originalias mokėjimų sumas/valiutas. '
                                                'Naudinga, kai yra sąskaitų, apmokėtų kita valiuta')
    show_accounts = fields.Boolean(string='Grupuoti pagal buhalterinę sąskaitą')
    dont_show_zero_values = fields.Boolean(string="Nerodyti nulinių įrašų", default=True)
    dont_show_zero_debts = fields.Boolean(string="Nerodyti įrašų be skolų", default=True)
    result_selection = fields.Selection(selection_add=[('all', 'Visos sumos')])

    @api.onchange('result_selection')
    def _onchange_result_selection(self):
        """
        Add a domain in selectable accounts based on result_selection type
        :return: field domain (dict)
        """
        if self.result_selection in ['customer_supplier']:
            return {'domain': {'account_ids': [('user_type_id.type', 'in', ['payable', 'receivable'])]}}
        elif self.result_selection in ['customer']:
            return {'domain': {'account_ids': [('user_type_id.type', 'in', ['receivable'])]}}
        elif self.result_selection in ['supplier']:
            return {'domain': {'account_ids': [('user_type_id.type', 'in', ['payable'])]}}
        else:
            return {'domain': {'account_ids': []}}

    @api.multi
    def check_report(self):
        res = super(AccountAgedTrialBalance, self).check_report()
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.multi
    def get_debt_act_wizard_values(self):
        self.ensure_one()
        if self.date:
            date_header = ' / {}'.format(self.date)
            self = self.with_context(date_header=date_header)
        if self.result_selection == 'customer':
            account_type = 'receivable'
        elif self.result_selection == 'supplier':
            account_type = 'payable'
        elif self.result_selection == 'customer_supplier':
            account_type = 'payable_receivable'
        else:
            account_type = 'all'
        vals = {
            'partner_ids': [(6, 0, self.filtered_partner_ids.ids)] if self.display_partner == 'filter' else False,
            'all_partners': True if self.display_partner == 'all' else False,
            'dont_show_zero_values': self.dont_show_zero_values,
            'dont_show_zero_debts': self.dont_show_zero_debts,
            'show_original_amounts': self.show_original_amounts,
            'show_accounts': self.show_accounts,
            'type': self.type,
            'date': self.date,
            'date_from': self.date_from_debt,
            'date_to': self.date_to,
            'detail_level': self.detail_level,
            'account_type_filter': account_type,
            'account_ids': [(6, 0, self.account_ids.ids)] if self.account_ids else False,
        }
        return vals

    @api.multi
    def _create_debt_act_wizard(self):
        self.ensure_one()
        vals = self.get_debt_act_wizard_values()
        lang = self.force_lang or self.env.user.lang or 'lt_LT'
        wiz_id = self.env['debt.act.wizard'].with_context(lang=lang).create(vals)
        return wiz_id

    @api.multi
    def create_debt_act_wizard(self):
        self.ensure_one()
        wiz_id = self._create_debt_act_wizard()
        if self._context.get('xls_export', False):
            return wiz_id.xls_export()
        res = wiz_id.generate_minimal_debt_act()
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.one
    def _compute_only_reduced(self):
        if self.env.user.only_reduced_debt_report() and not self.env.user.is_manager():
            self.only_reduced = True

    @api.onchange('invoices_only')
    def _onchange_invoice_only(self):
        if self.invoices_only:
            self.account_ids = None

    def _print_report(self, data):
        if self.only_reduced:
            self.result_selection = 'customer'
        res = {}
        data = self.pre_print_report(data)
        data['form'].update(self.read(['period_length'])[0])
        data['form']['display_partner'] = self.read(['display_partner'])[0]['display_partner']
        data['form']['filtered_partner_ids'] = self.filtered_partner_ids.ids
        data['form']['account_ids'] = self.account_ids.ids
        data['form']['invoices_only'] = self.invoices_only
        data['form']['include_proforma'] = self.include_proforma
        data['form']['short_report'] = self.short_report
        period_length = data['form']['period_length']
        if period_length <= 0:
            raise UserError(_('Privalote nustatyti trukmę ilgesnę negu 0.'))
        if not data['form']['date_from']:
            raise UserError(_('Privalote nustatyti pradžios datą.'))

        start = datetime.strptime(data['form']['date_from'], "%Y-%m-%d")

        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length - 1)
            res[str(i)] = {
                'name': (i != 0 and (str((5-(i+1)) * period_length) + '-' + str((5-i) * period_length))
                         or ('+' + str(4 * period_length))),
                'stop': start.strftime('%Y-%m-%d'),
                'start': (i != 0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop - relativedelta(days=1)
        data['form'].update(res)
        action_ref = 'sl_general_report.report_agedpartnerbalance_sl'
        return self.env['report'].with_context(landscape=True).get_action(self, action_ref, data=data)

    @api.multi
    def xls_export(self):
        return self.check_report()

    @api.multi
    def name_get(self):
        return [(rec.id, _('Skolų balansas')) for rec in self]


AccountAgedTrialBalance()
