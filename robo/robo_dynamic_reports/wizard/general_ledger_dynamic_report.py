# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, models, fields, api, tools
from odoo.addons.account_dynamic_reports.tools.format_tools import format_number_with_currency

FORCED_SUM_REPORT_COLUMNS = ['account_code', 'account', 'debit', 'credit', 'balance']


class GeneralLedgerDynamicReport(models.TransientModel):
    _name = 'general.ledger.dynamic.report'
    _inherit = ['dynamic.report', 'dynamic.report.threaded.report', 'account.report.general.ledger']

    _dr_base_name = _('General Ledger Report')
    _report_tag = 'dynamic.gl'

    account_ids = fields.Many2many(dynamic_report_front_filter=True)
    partner_ids = fields.Many2many(dynamic_report_front_filter=True)
    journal_ids = fields.Many2many(dynamic_report_front_filter=True, relation='general_ledger_dynamic_report_journal_rel',
                                   default=lambda self: self._default_journal_ids())

    @api.multi
    def get_report_columns(self):
        self.ensure_one()
        # Get columns shown based on report detail level
        if self.detail_level == 'detail':
            columns_to_show = ['date', 'journal_id', 'partner_id', 'reference', 'entry', 'entry_label', 'debit',
                               'credit', 'balance', 'currency']
            # Get any other columns the user wishes to see
            columns_to_show += self.env['dynamic.report.user.column.settings'].search([
                ('shown', '=', True),
                ('settings_id.report_model_id.model', '=', self._name),
                ('settings_id.settings_id.user_id', '=', self._uid)
            ]).mapped('column_id.identifier')
        else:
            columns_to_show = FORCED_SUM_REPORT_COLUMNS
            if self.initial_balance:
                columns_to_show.append('initial_balance')
        extra_domain = [('identifier', 'in', columns_to_show)]
        return super(GeneralLedgerDynamicReport, self).get_report_columns(extra_domain)

    @api.multi
    def get_shown_column_data(self):
        self.ensure_one()
        if self.detail_level == 'detail':
            return super(GeneralLedgerDynamicReport, self).get_shown_column_data()
        column_data = self.get_report_column_data()
        columns_to_show = FORCED_SUM_REPORT_COLUMNS
        if self.initial_balance:
            columns_to_show.append('initial_balance')
        columns = [column for column in column_data if column.get('shown') or
                   column.get('identifier') in columns_to_show]
        for column in columns:
            column['calculate_totals'] = False  # Don't calculate totals for any of the columns for sum report
            if column.get('identifier') in columns_to_show:
                column['shown'] = True  # Force show forced sum report columns
        if not columns:
            columns = [column for column in column_data if column.get('shown_by_default')]
        return columns

    @api.multi
    def get_report_column_data(self):
        self.ensure_one()
        if self.detail_level == 'detail':
            return super(GeneralLedgerDynamicReport, self).get_report_column_data()
        column_data = self.get_report_columns().read()
        report_settings = self.get_report_settings()
        columns_to_show = FORCED_SUM_REPORT_COLUMNS
        if self.initial_balance:
            columns_to_show.append('initial_balance')
        if report_settings:
            shown_column_identifiers = report_settings.get_shown_column_identifiers()
            index_map = {v: i + 1 for i, v in enumerate(shown_column_identifiers)}
            column_data.sort(key=lambda x: index_map.get(x.get('identifier'), True))
            for column in column_data:
                column['shown'] = bool(index_map.get(column.get('identifier'), False) or
                                       column.get('identifier') in columns_to_show)
                column['calculate_totals'] = False  # Don't calculate totals for any of the columns for sum report
        return column_data

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        report_action = self.check_report()
        data = report_action.get('data', {})
        form_data = data.get('form')
        if form_data:
            form_data['display_account'] = 'filter' if form_data.get('filtered_account_ids').get('filtered_account_ids') else self.display_account
            form_data['display_partner'] = 'filter' if form_data.get('filtered_partner_ids') else self.display_partner
            data['form'] = form_data
        report_data = self.env['report.sl_general_report.report_generalledger_sl'].get_html_report_data(
            doc_ids=None, data=data
        )
        accounts = report_data.get('Accounts')
        account_move_line_action = self.env.ref('l10n_lt.account_move_line_robo_front_action', False)
        account_move_action = self.env.ref('l10n_lt.account_move_line_robo_front_action', False)
        company_currency = self.env.user.company_id.currency_id
        if self.detail_level == 'detail':
            res = list()
            for account in accounts:
                move_lines = account.get('move_lines', list())
                currency_codes = list(set([x.get('currency_code') for x in move_lines if x.get('currency_code')]))
                currencies = self.env['res.currency'].search([('symbol', 'in', currency_codes)])
                for move_line in move_lines:
                    currency = currencies.filtered(lambda c: c.symbol == move_line['currency_code'])
                    currency = (currency and currency[0]) or company_currency
                    aml_ids = move_line.get('line_ids', [])
                    aml_id = move_line.get('lid')
                    ldate = move_line.get('ldate')
                    date = datetime.strptime(move_line['ldate'], tools.DEFAULT_SERVER_DATE_FORMAT) if ldate else None
                    if aml_id:
                        aml_ids.append(aml_id)
                    res.append({
                        '__record_data__': {
                            'record_model': 'account.move.line',
                            'record_ids': aml_ids,
                            'action_id': account_move_line_action.id if account_move_line_action else None
                        },
                        'date': {
                            'value': move_line['ldate']
                        },
                        'journal_id': {
                            'value': move_line['lcode']
                        },
                        'partner_id': {
                            'value': move_line['partner_name']
                        },
                        'reference': {
                            'value': move_line['lref']
                        },
                        'entry': {
                            'value': move_line['move_name']
                        },
                        'entry_label': {
                            'value': move_line['lname'],
                        },
                        'debit': {
                            'value': move_line['debit'],
                            'currency_id': currency.id,
                        },
                        'credit': {
                            'value': move_line['credit'],
                            'currency_id': currency.id,
                        },
                        'balance': {
                            'value': move_line['balance'],
                            'account_balance': account.get('balance'),
                            'currency_id': currency.id,
                        },
                        'currency': {
                            'value': move_line['currency_code'] or company_currency.name,
                        },
                        'account_id': {
                            'value': account['code'],
                            'name': '{} - {}'.format(account['code'], account['name'])
                        },
                        'year': {
                            'value': str(date.year if date else ""),
                        },
                        'month': {
                            'value': str(date.month if date else ""),
                        },
                        'account_code': {
                            'value': account.get('code')
                        },
                        'account': {
                            'value': account.get('name')
                        },
                    })
            return res
        else:
            return [{
                '__record_data__': {
                    'record_model': 'account.move',
                    'record_ids': [account.get('id')],
                    'action_id': account_move_action.id if account_move_action else None
                },
                'account_code': {
                    'value': account.get('code')
                },
                'account': {
                    'value': account.get('name')
                },
                'debit': {
                    'value': account.get('debit'),
                    'currency_id': company_currency.id,
                },
                'credit': {
                    'value': account.get('credit'),
                    'currency_id': company_currency.id,
                },
                'balance': {
                    'value': account.get('balance'),
                    'currency_id': company_currency.id,
                },
                'account_id': {
                    'value': account.get('code'),
                    'display_value': '{} - {}'.format(account.get('code'), account.get('name'))
                },
                'initial_balance': {
                    'value': account.get('init_balance'),
                    'currency_id': company_currency.id,
                }
            } for account in accounts]

    @api.multi
    def action_view(self):
        self.ensure_one()
        self._check_if_threaded_reports_are_enabled()
        return super(GeneralLedgerDynamicReport, self).action_view()

    @api.multi
    def get_render_data(self, language=None):
        def find_and_update_balance_data(subgroup, balance_column_index, hide_balance=True):
            """
            Updates balance for provided group and each subgroup since it's a value on a specific account and not
            the sum of account move lines
            """
            for s_group in subgroup.get('subgroups', list()):
                # Update balance for each subgroup
                find_and_update_balance_data(s_group, balance_column_index, hide_balance)
            child_elements = list(subgroup.get('children', list()))
            if not child_elements or 'group_totals' not in subgroup:
                return

            # Hide balance if the group identifier is not the account id
            if hide_balance or subgroup.get('group_by_identifier') != 'account_id':
                subgroup['group_totals'][balance_column_index]['total'] = ''

            # Account balance data is stored on each child element
            balance_data = child_elements[0].get('data', dict()).get('balance', dict())
            balance, currency_id = balance_data.get('account_balance'), balance_data.get('currency_id')
            if not balance:
                return

            # Set the balance as the group total
            currency = self.env['res.currency'].sudo().browse(currency_id)
            language = self.env['res.lang'].sudo().search([('code', '=', self.determine_language_code())], limit=1)
            balance = format_number_with_currency(balance, currency, language)
            subgroup['group_totals'][balance_column_index]['total'] = balance

        res = super(GeneralLedgerDynamicReport, self).get_render_data(language)

        account_group_by_identifiers = self.get_stored_group_by_identifiers()
        if 'account_id' not in account_group_by_identifiers:
            return res

        first_field_to_group_by_is_account_id = account_group_by_identifiers[0] == 'account_id'

        column_identifiers = [(c.get('identifier'), c.get('calculate_totals', False)) for c in res.get('column_data')]
        columns_to_calculate_totals_for = [c[0] for c in column_identifiers if c[1]]
        if 'balance' in columns_to_calculate_totals_for:
            balance_total_column_index = columns_to_calculate_totals_for.index('balance')
            # Find and update last balance for this group and each subgroup
            find_and_update_balance_data(res, balance_total_column_index, not first_field_to_group_by_is_account_id)
        return res

    @api.model
    def prepare_xlsx_data(self):
        res = super(GeneralLedgerDynamicReport, self).prepare_xlsx_data()
        columns = res.get('columns', list())
        for column in columns:
            if column.get('identifier') == 'balance':
                # Don't calculate totals for balance column since it should not be the total of child elements
                column['calculate_totals'] = False
        return res
