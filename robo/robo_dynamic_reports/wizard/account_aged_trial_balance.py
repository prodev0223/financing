# -*- coding: utf-8 -*-

from odoo import models, fields, _, api


class AccountAgedTrialBalance(models.TransientModel):
    _name = 'account.aged.trial.balance'
    _inherit = ['account.aged.trial.balance', 'dynamic.report']

    _dr_base_name = _('Account aged trial balance')
    _report_tag = 'dynamic.aatb'

    @api.multi
    def name_get(self):
        res = list()
        for rec in self:
            report_name = rec._dr_base_name
            if rec.date_from:
                report_name += ' {}'.format(rec.date_from)
            res.append((rec.id, report_name))
        return res

    filtered_partner_ids = fields.Many2many('res.partner', dynamic_report_front_filter=True)
    invoices_only = fields.Boolean(dynamic_report_front_filter=True)
    include_proforma = fields.Boolean(dynamic_report_front_filter=True)
    account_ids = fields.Many2many('account.account', dynamic_report_front_filter=True)
    result_selection = fields.Selection(dynamic_report_front_filter=True)
    date_range = fields.Selection(default=False, dynamic_report_front_filter=False)
    date_from = fields.Date(string="Debts for date")
    date_to = fields.Date(dynamic_report_front_filter=False)
    period_length = fields.Integer(dynamic_report_front_filter=True)
    short_report = fields.Boolean(dynamic_report_front_filter=True)

    @api.model
    def default_get(self, field_list):
        res = super(AccountAgedTrialBalance, self).default_get(field_list)
        report_type = res.get('report_type')
        if report_type:
            subtype = res.get('type')
            res['date_range'], res['date_from'], res['date_to'] = self.get_default_dates_based_on_report_type(
                report_type, subtype)
        return res

    @api.onchange('report_type', 'type')
    def _set_default_dates_based_on_report_types(self):
        self.date_range, self.date_from, self.date_to = self.get_default_dates_based_on_report_type(
            self.report_type, self.type)

    @api.model
    def get_default_dates_based_on_report_type(self, report_type, subtype):
        if report_type == 'aged_balance' or subtype != 'all':
            date_range = 'today'
        else:
            date_range = 'this_fiscal_year'
        date_from, date_to = self.get_dates_from_range(date_range)
        return date_range, date_from, date_to

    @api.multi
    def action_view(self):
        self.ensure_one()
        if self.report_type == 'debt_act':
            wizard = self._create_debt_act_wizard()
            return wizard.action_view()
        return super(AccountAgedTrialBalance, self).action_view()

    @api.multi
    def get_report_data(self):
        self.ensure_one()
        self.write({
            # Adjust display partner selection that is not really necessary but report data still checks it
            'display_partner': 'all' if not self.filtered_partner_ids else 'filter',
            'date_from_debt': self.date_from,
            'date': self.date_from
        })
        return super(AccountAgedTrialBalance, self).get_report_data()

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        res = []

        # Get form data
        data = self.check_report().get('data', {})

        # Add language to context
        context = self._context.copy()
        context['lang'] = self.determine_language_code()

        # Get actual report data
        ReportObj = self.env['report.sl_general_report.report_agedpartnerbalance_sl']
        render_data = ReportObj.with_context(context).get_full_render_data(self.ids, data)

        # Find bracket columns
        bracket_columns = self.get_report_columns([('identifier', 'like', 'bracket_')]).sorted(
            key=lambda col: col.identifier
        )
        bracket_ids = [int(bracket_column.identifier.replace('bracket_', '')) for bracket_column in bracket_columns]

        lines = render_data.get('get_partner_lines', [])
        if isinstance(lines, dict):
            lines = [lines]
        res += self.get_partner_line_data(lines, bracket_ids)

        invoices = render_data.get('invoices')
        invoice_rows = invoices.get('rows', []) if invoices else []

        res += self.get_invoice_row_data(invoice_rows, bracket_ids)

        return res

    @api.model
    def get_partner_line_data(self, partner_lines, bracket_ids):
        res = []
        company_currency = self.env.user.company_id.currency_id

        partners = self.env['res.partner'].browse([partner.get('partner_id') for partner in partner_lines])
        mapper_partner_id_to_country = {partner.id: partner.country_id.name for partner in partners}

        for line in partner_lines:
            processed_line_values = {
                '__record_data__': {
                    'record_ids': line.pop('record_ids', None),
                    'record_model': 'account.move.line'
                },
                'partner_id': {'value': line.get('name')},
                'not_due': {'value': line.pop('direction', 0.0), 'currency_id': company_currency.id},
                'partner_country': {'value': mapper_partner_id_to_country.get(line.get('partner_id'))},
            }

            if self.short_report:
                processed_line_values['group_id'] = {'value': line.get('title') or line.get('name')}

            # Add value for each bracket
            for bracket_id in bracket_ids:
                # Bracket position is the reverse of the bracket id
                bracket_position = str(max(bracket_ids) - bracket_id)
                processed_line_values['bracket_{}'.format(bracket_id)] = {
                    'value': line.pop(bracket_position, 0.0),
                    'currency_id': company_currency.id
                }

            # Some keys match the returned data so just add them to line values
            matching_keys = ['email', 'phone', 'total']
            for matching_key in matching_keys:
                processed_line_values[matching_key] = {'value': line.pop(matching_key, None)}

            # Set currency for the totals column/values
            processed_line_values['total']['currency_id'] = company_currency.id

            res.append(processed_line_values)
        return res

    @api.model
    def get_invoice_row_data(self, invoice_rows, bracket_ids):
        res = []
        company_currency = self.env.user.company_id.currency_id
        for invoice_row in invoice_rows:
            processed_row_values = {
                'partner_id': {'value': invoice_row.get('partner_name')},
                'not_due': {'value': invoice_row.pop('no_delay', 0.0), 'currency_id': company_currency.id},
                'total': {'value': invoice_row.pop('total', 0.0), 'currency_id': company_currency.id},
                'phone': {'value': invoice_row.pop('partner_phone', None)},
                'email': {'value': invoice_row.pop('partner_mail', None)},
                'invoice_id': {'value': invoice_row.pop('invoice_name', None)},
                '__record_data__': {
                    'record_ids': [invoice_row.pop('record_id', None)],
                    'record_model': invoice_row.pop('record_model', None)
                },
            }

            if self.short_report:
                processed_row_values['group_id'] = {
                    'value': invoice_row.get('title') or invoice_row.get('name') or invoice_row.get('partner_name')
                }

            # Add value for each bracket
            for bracket_id in bracket_ids:
                # Bracket position is the reverse of the bracket id
                bracket_position = str(max(bracket_ids) - bracket_id)
                processed_row_values['bracket_{}'.format(bracket_id)] = {
                    'value': invoice_row.pop(bracket_position, 0.0),
                    'currency_id': company_currency.id
                }

            res.append(processed_row_values)
        return res

    @api.multi
    def get_report_column_data(self):
        """
        Extend the parent method that returns column data to show only applicable columns for each report type.
        """
        self.ensure_one()
        res = super(AccountAgedTrialBalance, self).get_report_column_data()

        # Determine which columns are brackets
        bracket_column_identifiers = [col.get('identifier') for col in res if 'bracket_' in col.get('identifier')]
        bracket_column_identifiers.sort()  # Sort for later

        allowed_column_identifiers = ['not_due', 'total']
        if self.short_report:
            allowed_column_identifiers.append('group_id')
        else:
            allowed_column_identifiers += ['partner_id', 'partner_country', 'email', 'phone']

        if self.invoices_only:
            allowed_column_identifiers += ['invoice_id']
        allowed_column_identifiers += bracket_column_identifiers

        res = [col for col in res if col.get('identifier') in allowed_column_identifiers]

        # Adjust shown columns
        for col in res:
            column_identifier = col.get('identifier')

            # Adjust bracket column names with the day period identifiers
            if column_identifier in bracket_column_identifiers:
                last_bracket_identifier = bracket_column_identifiers[-1]
                bracket_id = int(column_identifier.replace('bracket_', ''))
                day_period_min = bracket_id * self.period_length
                if column_identifier == last_bracket_identifier:
                    col['name'] = '+{}'.format(day_period_min)                    # +90
                else:
                    day_period_max = (bracket_id+1) * self.period_length
                    col['name'] = '{}-{}'.format(day_period_min, day_period_max)  # 0-30, 30-60, 60-90, etc.

        return res

    @api.multi
    def action_pdf(self, data=None, sort_by=None):
        self.ensure_one()
        self = self._update_self_with_report_language()
        if self.report_type == 'aged_balance':
            return super(AccountAgedTrialBalance, self).action_pdf(data, sort_by)
        wizard = self._create_debt_act_wizard()
        return wizard.action_pdf(data, sort_by)

    @api.multi
    def action_xlsx(self, data=None, sort_by=None):
        self.ensure_one()
        self = self._update_self_with_report_language()
        if self.report_type == 'aged_balance':
            return super(AccountAgedTrialBalance, self).action_xlsx(data, sort_by)
        wizard = self._create_debt_act_wizard()
        return wizard.action_xlsx(data, sort_by)

    @api.multi
    def get_debt_act_wizard_values(self):
        self.ensure_one()
        res = super(AccountAgedTrialBalance, self).get_debt_act_wizard_values()
        # Adjust debt act wizard values since the wizard was changed and unnecessary fields were removed
        res.update({
            'partner_ids': [(6, 0, self.filtered_partner_ids.ids)] if self.filtered_partner_ids else False,
            'all_partners': not self.filtered_partner_ids,
            'date_from': self.date_from,
            'date': self.date_from,
            'date_range': self.date_range,
            'force_lang': self.report_language,
            'report_language': self.report_language,
        })
        return res
