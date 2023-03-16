# -*- coding: utf-8 -*-
import datetime
from odoo import api, fields, models, _


class AccountCashflowReport(models.TransientModel):

    _name = 'account.cashflow.report'
    _inherit = 'account.common.report'

    def _date_to_default(self):
        return datetime.datetime.utcnow()

    def _date_from_default(self):
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from']

    date_from = fields.Date(required=True, default=_date_from_default)
    date_to = fields.Date(required=True, default=_date_to_default)
    hierarchy_level = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'),
                                        ('6', '6'), ('7', '7')],
                                       # ('not_zero', 'With balance is not equal to 0'),
                                       string='Hierarchy Level', required=True, default='1')

    def _print_report(self, data):
        ctx = self._context.copy()
        user = self.env.user
        company = user.company_id
        lang = company.partner_id.lang if company.partner_id.lang else ctx.get('lang')
        ctx.update({'lang': self.force_lang or lang})
        self = self.with_context(ctx)
        data['form'].update({'robo_front': ctx.get('robo_front')})
        data['form'].update(self.read(['target_move', 'hierarchy_level'])[0])
        return self.env['report'].get_action(self, 'sl_general_report.report_cashflowstatement_sl', data=data)

    @api.multi
    def check_report(self):
        res = super(AccountCashflowReport, self).check_report()
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res
    
    @api.multi
    def xls_export(self):
        return self.check_report()

    @api.multi
    def name_get(self):
        return [(rec.id, _('Pinigų srautai')) for rec in self]


AccountCashflowReport()
