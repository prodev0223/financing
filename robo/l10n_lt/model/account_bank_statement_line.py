# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    date = fields.Date(lt_string='Data')
    amount_currency = fields.Monetary(lt_string='Suma (Valiuta)')
    currency_id = fields.Many2one('res.currency', lt_string='Valiuta')
    amount = fields.Monetary(lt_string='Suma')
    bank_account_id = fields.Many2one('res.partner.bank', lt_string='Banko sąskaita')

    def get_statement_line_for_reconciliation_widget(self):
        res = super(AccountBankStatementLine, self).get_statement_line_for_reconciliation_widget()
        name = res.get('name') or ''
        if 'valiutos konvertavimas' in name.lower():
            transfer_account_id = self.env['account.account'].search([('code', '=', '273')], limit=1)  # pinigai kelyje
            if transfer_account_id:
                res['open_balance_account_id'] = transfer_account_id.id
        return res
