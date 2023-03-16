# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.tools.misc import formatLang

INVOICE_TYPE_MAPPING = {
    'sale': ['out_invoice', 'out_refund'],
    'purchase': ['in_invoice', 'in_refund'],
}


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.multi
    def get_journal_dashboard_datas(self):
        self.ensure_zero_or_one()
        res = super(AccountJournal, self).get_journal_dashboard_datas()
        num_not_validated = sum_not_validated = 0
        # Check non validated invoices not validated invoices
        if self.type in ['sale', 'purchase']:
            self.env.cr.execute('''
            SELECT COUNT(ID) as count, SUM(amount_total_company_signed) as amount_total_company_signed
                FROM account_invoice
            WHERE
                accountant_validated = false AND
                state NOT IN ('proforma', 'proforma2') AND
                journal_id = %s AND
                type IN %s
            ''', (self.id, tuple(INVOICE_TYPE_MAPPING[self.type])))
            r = self.env.cr.dictfetchone()
            num_not_validated = r.get('count')
            sum_not_validated = r.get('amount_total_company_signed') or 0.0
        res['num_not_validated'] = num_not_validated
        res['sum_not_validated'] = formatLang(
            self.env, sum_not_validated,
            currency_obj=self.currency_id or self.company_id.currency_id
        )
        return res

    @api.multi
    def get_last_balance(self):
        domain = [('journal_id', 'in', self.ids)]
        if self.type == 'bank':
            domain += [('sepa_imported', '=', True)]
        last_bank_stmt = self.env['account.bank.statement'].search(domain, order="date desc, id desc", limit=1)
        last_balance = last_bank_stmt and last_bank_stmt[0].balance_end or 0
        return last_balance

    @api.multi
    def open_action(self):
        action = super(AccountJournal, self).open_action()
        if self.type == 'bank':
            action['context'].update(search_default_imported=1)
        return action

    @api.multi
    def open_action_with_context(self):
        action_name = self.env.context.get('action_name', False)
        action = super(AccountJournal, self).open_action_with_context()
        if action_name == 'action_bank_statement_line':
            action['context'].update(search_default_imported=1)
        return action


AccountJournal()
