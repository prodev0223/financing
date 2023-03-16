# -*- coding: utf-8 -*-

from odoo import models, _, api
from odoo.tools import float_is_zero
from debt_reconciliation_base import get_data_by_account_code
from odoo.tools.misc import formatLang


class DebtReconciliationMinimal(models.AbstractModel):

    """
    Debt reconciliation minimal report -- Used in wizard reports
    """

    _inherit = ['report.debt.reconciliation.base']
    _name = 'report.skolu_suderinimas.report_aktas_multi_minimal'

    def _get_bare_currency_data(self, currency_id):
        currency = self.env['res.currency'].browse(currency_id)
        show_name = True if (self.env['res.currency'].search_count([('symbol', '=', currency.symbol)]) > 1) else False
        if not currency:
            data = {
                'display_name': 'Valiuta',
                'position': 'after',
                'symbol': 'Valiuta',
                'show_name': False,
            }
        else:
            data = {
                'display_name': currency.display_name,
                'position': currency.position,
                'symbol': currency.symbol,
                'show_name': show_name
            }
        return data

    def _get_account_name(self, account_code):
        return '%s %s' % (account_code,
                          self.env['account.account'].search([('code', '=', account_code)], limit=1).name or '')

    def _get_partner_data(self, partner_id):
        return self.env['res.partner'].browse(partner_id)

    @api.multi
    def render_html(self, doc_ids, data=None):
        lang = data.get('force_lang') or self.env.user.lang or 'lt_LT'
        self = self.with_context(lang=lang, force_lang=lang)
        report_obj = self.env['report'].sudo()
        report = report_obj._get_report_from_name('skolu_suderinimas.report_aktas_multi_minimal')
        partner_ids = set(data['partner_ids'])
        partners = self.sudo().env['res.partner'].browse(partner_ids)
        date = data['date']
        date_from = data['date_from']
        date_to = data['date_to']
        original_amount_group_by = data['show_original_amounts']
        default_account_domain = data.get('account_ids') if data.get(
            'account_ids') else self.get_default_payable_receivable(mode=data['account_type_filter'])

        report_type = data['type']
        data_by_partner_id = {
            partner_id: self.sudo().get_all_account_move_line_data(
                partner_id, default_account_domain, report_type, date, date_from, date_to, original_amount_group_by
            ) for partner_id in partner_ids
        }

        if data['dont_show_zero_debts']:
            for partner in partners:
                if all(float_is_zero(data_by_partner_id[partner.id][currency]['debit'] -
                                               data_by_partner_id[partner.id][currency]['credit'], precision_digits=2)
                             for currency in data_by_partner_id[partner.id]):
                    data_by_partner_id.pop(partner.id, False)

        if data['dont_show_zero_values']:
            for partner in partners:
                partner_data = data_by_partner_id.get(partner.id)
                if not partner_data:
                    continue
                credit_debit_value = 0
                for currency in partner_data:
                    credit_debit_value += partner_data[currency]['credit']
                    credit_debit_value -= partner_data[currency]['debit']
                if float_is_zero(credit_debit_value, precision_digits=2):
                    data_by_partner_id.pop(partner.id, False)

        data_by_account_code = {}
        if data['detail_level'] == 'sum' and data['show_accounts']:
            data_by_account_code = get_data_by_account_code(data_by_partner_id)
        partner_ids = data_by_partner_id.keys()

        docargs = {
            'doc_ids': partner_ids,
            'doc_model': report.model,
            'docs': self.env['res.partner'].browse(partner_ids),
            'date': data['date'],
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'data_by_partner_id': data_by_partner_id,
            'data_by_account_code': data_by_account_code,
            'company': self.env.user.company_id,
            'get_bare_currency_data': self._get_bare_currency_data,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'get_partner_data': self._get_partner_data,
            'get_account_name': self._get_account_name,
            'type': data['type'],
            'detail_level': data['detail_level'],
            'account_type_filter': data['account_type_filter'],
            'original_amount_group_by': original_amount_group_by,
            'show_accounts': data['show_accounts'],
            'payment_reminder': data.get('payment_reminder', False),
        }
        return report_obj.render('skolu_suderinimas.report_aktas_multi_minimal', docargs)


DebtReconciliationMinimal()
