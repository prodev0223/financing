# -*- coding: utf-8 -*-

from odoo import models, api, _, fields, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class KasosKnygaReport(models.TransientModel):

    _name = 'kasos.knyga.report'

    @api.model
    def get_journal_domain(self):
        """Returns domain for current model's journal_id field based on the user"""
        domain = [('type', '=', 'cash'), ('skip_cash_reports', '=', False)]
        if not self.env.user.has_group('robo_basic.group_robo_cash_manager') \
                and not self.env.user.has_group('robo_basic.group_robo_premium_manager'):
            # If user is not cash manager and not the premium manager,
            # filter out the journals that have no person assigned to them
            domain += [('id', 'in', self.env.user.cash_register_journal_ids.ids)]
        return domain

    def _date_from(self):
        return (datetime.now() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _date_to(self):
        return (datetime.now() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def _default_journal_id(self):
        """Returns default journal ID """
        return self.env['account.journal'].search(self.get_journal_domain(), limit=1)

    date_from = fields.Date(string='Data nuo', required=True, default=_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=_date_to)
    include_canceled = fields.Boolean(string='Įtraukti anuliuotus įrašus', default=True)
    journal_id = fields.Many2one(
        'account.journal', string='Kasos žurnalas',
        required=True, default=_default_journal_id,
        domain="[('type','=','cash'), ('skip_cash_reports', '=', False)]"
    )
    code = fields.Char(related='journal_id.code')
    payment_type_filter = fields.Selection([
        ('all', 'All'),
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Payment type', default='all')

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """
        Onchange trigger on journal ID - meant to return the domain
        to the field based on user groups and/or controlled journals.
        :return: None
        """
        # Field has the same domain, but for safety reasons
        # it's not removed from the definition
        return {'domain': {'journal_id': self.get_journal_domain()}}

    @api.multi
    def name_get(self):
        return [(rec.id, _('Kasos knyga')) for rec in self]

    def _print_report(self, data, template):
        if not self.journal_id.default_debit_account_id and not self.journal_id.default_credit_account_id:
            raise exceptions.ValidationError(_('Nenurodytos žurnalo debetinė ir kreditinė sąskaitos'))
        return self.env['report'].get_action(self, template, data=data)

    @api.multi
    def check_report(self):
        self.ensure_one()
        if self.journal_id.code == 'KVIT':
            template = 'sl_general_report.report_cash_receipt_template'
            additional_field = 'payment_type_filter'
        else:
            template = 'sl_general_report.report_kasos_knyga_template'
            additional_field = 'include_canceled'

        data = {
            'ids': self.env.context.get('active_ids', []),
            'model': self.env.context.get('active_model', 'ir.ui.menu'),
            'form': self.read(['date_from', 'date_to', 'journal_id', 'include_canceled', additional_field])[0],
        }
        # used_context = self._build_contexts(data)
        # data['form']['used_context'] = dict(used_context, lang=self.env.context.get('lang', 'en_US'))
        res = self._print_report(data, template=template)
        if 'report_type' in res:
            if self._context.get('force_pdf'):
                res['report_type'] = 'qweb-pdf'
            if self._context.get('force_html'):
                res['report_type'] = 'qweb-html'
        return res

    @api.multi
    def xls_export(self):
        if self.date_to or self.date_from:
            date_header = ' / {} - {}'.format(self.date_from or '', self.date_to or '')
            self = self.with_context(date_header=date_header)
        return self.check_report()


KasosKnygaReport()
