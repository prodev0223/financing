# -*- coding: utf-8 -*-

from six import iteritems

from odoo import _, models, fields, api


class AccountingReport(models.TransientModel):
    _name = 'accounting.report'
    _inherit = ['accounting.report', 'dynamic.report']

    _dr_base_name = _('Accounting report')

    date_to = fields.Date(string='Date')
    uab_report_size = fields.Selection()
    accounting_report_type = fields.Char()
    date_range = fields.Selection(default='')

    @api.multi
    def action_view(self):
        self.ensure_one()

        self.update_accounting_report_type_based_on_context()

        action_res = super(AccountingReport, self).action_view()

        if self.accounting_report_type == 'balance':
            title = _('Balance view')
            tag = 'dynamic.dbar'
        else:
            title = _('Profit/Loss')
            tag = 'dynamic.pl'
        action_res['name'] = title
        action_res['context']['title'] = title
        action_res['tag'] = tag

        return action_res

    @api.multi
    def update_accounting_report_type_based_on_context(self):
        """
            Updates accounting report type based on context. Used to determine which dynamic views and fields to show
        """
        accounting_report_type = ''
        if self._context.get('pelnas'):
            accounting_report_type = 'profit/loss'
        elif self._context.get('balansas'):
            accounting_report_type = 'balance'
        self.write({'accounting_report_type': accounting_report_type})

    @api.multi
    def get_base_context(self):
        if self.accounting_report_type == 'balance':
            return {'balansas': 1}
        else:
            return {'pelnas': 1}

    @api.multi
    def check_report(self):
        self.update_force_lang()
        return super(AccountingReport, self).check_report()

    @api.multi
    def update_force_lang(self):
        for rec in self:
            rec.write({'force_lang': rec.report_language})

    @api.multi
    def action_pdf(self):
        self = self._update_self_with_report_language()
        context = self._context.copy()
        context.update(self.get_base_context())
        context.update({
            'force_pdf': True,
            'front': True
        })
        return self.with_context(context).check_report()

    @api.multi
    def action_xlsx(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        context = self._context.copy()
        context.update(self.get_base_context())
        context.update({'front': True})
        return self.with_context(context).xls_export()

    @api.multi
    def update_report_filters(self, filters):
        self.ensure_one()
        res = super(AccountingReport, self).update_report_filters(filters)
        context = self._context.copy()
        context.update(self.get_base_context())
        self.with_context(context).get_report_id()
        return res

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        # Get original accounting report data
        context = self._context.copy()
        context.update(self.get_base_context())
        context.update({'front': True, 'force_html': True})
        data = self.with_context(context).check_report()
        form = data.get('data', {}).get('form')

        # Get data
        ReportObj = self.env['report.sl_general_report.report_financial_sl']
        account_lines = ReportObj.get_account_lines(form)

        # Sort lines just as in the original report
        account_lines.sort(key=lambda l: (l.get('sequence', 0), l.get('code', '0')))

        # Determine levels
        levels = list(set([account_line.get('level', 0) for account_line in account_lines]))
        levels.sort()

        # Convert account line values to dynamic report data format
        res = [{
            key: {'value': value} for key, value in iteritems(account_line)
        } for account_line in account_lines]

        # Include additional data
        company_currency = self.env.user.company_id.currency_id

        account_move_line_action = self.env.ref('l10n_lt.account_move_line_robo_front_action', False)

        for account_line in res:
            # Update currency
            currency_id = account_line.get('currency_id', {}).get('value') or company_currency.id
            account_line['balance']['currency_id'] = currency_id
            move_line_ids = account_line.get('move_line_ids', {}).get('value')

            # Update record data
            if move_line_ids:
                record_data = account_line.get('__record_data__', {})
                if not record_data or not record_data.get('record_ids'):
                    record_data.update({
                        'record_model': 'account.move.line',
                        'record_ids': move_line_ids,
                        'action_id': account_move_line_action.id if account_move_line_action else None
                    })
                    account_line['__record_data__'] = record_data

        return res

    @api.multi
    def get_report_sorting(self):
        self.ensure_one()
        return [{'field': 'sequence', 'direction': 'ascending'}]  # Force report sorting

    @api.multi
    def _get_dynamic_report_front_filter_fields(self):
        """
            Force dynamic report front filter fields since multiple reports have same model
        """
        self.ensure_one()
        if self.accounting_report_type == 'balance':
            return ['date_to', 'uab_report_size']
        else:
            return ['date_from', 'date_to', 'reduced_uab_report']