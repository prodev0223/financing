# -*- coding: utf-8 -*-

from odoo import models, api, _
from debt_reconciliation_base import _format_text, get_data_by_account_code
from odoo.tools.misc import formatLang


class PartnerBalance(models.AbstractModel):

    """
    Debt reconciliation report -- Used when debt report is being sent via email
    """

    _inherit = ['report.debt.reconciliation.base']
    _name = 'report.skolu_suderinimas.report_aktas_multi'

    def _get_currency_name(self, currency_id):
        return self.env['res.currency'].browse(currency_id).name or _('Valiuta')

    def _get_account_name(self, account_code):
        return '%s %s' % (account_code,
                          self.env['account.account'].search([('code', '=', account_code)], limit=1).name or '')

    def _get_partner_data(self, partner_id):
        return self.env['res.partner'].browse(partner_id)

    def _get_accountant(self):
        current_user = self.env.user
        accountant = current_user if current_user.is_accountant() and not current_user.has_group('base.group_system') \
            else current_user.sudo().company_id.findir
        return accountant

    @api.model
    def get_report_data(self, data):
        partner_ids = data['partner_ids'] or data.get('context', {}).get('partner_ids', [])
        date = data['date']
        date_from = data['date_from']
        date_to = data['date_to']
        default_account_domain = data.get('account_ids') if data.get(
            'account_ids') else self.get_default_payable_receivable(mode=data['account_type_filter'])
        show_original_amounts = data.get('show_original_amounts', False)
        report_type = data['type']
        data_by_partner_id = {}
        for partner_id in partner_ids:
            data_by_partner_id[partner_id] = self.get_all_account_move_line_data(
                partner_id, default_account_domain, report_type, date, date_from, date_to, show_original_amounts)

        data_by_account_code = {}
        if data['detail_level'] == 'sum' and data['show_accounts']:
            data_by_account_code = get_data_by_account_code(data_by_partner_id)
        return data_by_partner_id, data_by_account_code

    @api.multi
    def render_html(self, doc_ids, data=None):
        report_obj = self.env['report']
        report = report_obj._get_report_from_name('skolu_suderinimas.report_aktas_multi')

        if self.env.user.is_manager() or self.env.user.has_group('robo.group_menu_kita_analitika'):
            self = self.sudo()

        partner_ids = data['partner_ids'] or data.get('context', {}).get('partner_ids', [])
        partners = self.env['res.partner'].browse(partner_ids)
        accountant = self._get_accountant()

        data_by_partner_id, data_by_account_code = self.get_report_data(data)

        docargs = {
            'doc_ids': partner_ids,
            'doc_model': report.model,
            'docs': partners,
            'date': data['date'],
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'accountant': accountant,
            'current_user_timestamp': self.env.user.get_current_timestamp(),
            'data_by_partner_id': data_by_partner_id,
            'data_by_account_code': data_by_account_code,
            'company': self.env.user.company_id,
            'get_currency_name': self._get_currency_name,
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'get_partner_data': self._get_partner_data,
            'get_account_name': self._get_account_name,
            'type': data['type'],
            'detail_level': data['detail_level'],
            'account_type_filter': data['account_type_filter'],
            'show_original_amounts': data['show_original_amounts'],
            'show_accounts': data['show_accounts'],
            'payment_reminder': data.get('payment_reminder', False),
            'forced_amount': data.get('forced_amount', None),
            'format_text': _format_text,
        }
        return report_obj.render('skolu_suderinimas.report_aktas_multi', docargs)


PartnerBalance()
