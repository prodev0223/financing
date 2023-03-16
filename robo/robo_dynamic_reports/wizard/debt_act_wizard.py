# -*- coding: utf-8 -*-
from six import iteritems

from odoo import models, _, api, fields, exceptions, tools


class AccReportGeneralLedgerSL(models.TransientModel):
    _name = 'debt.act.wizard'
    _inherit = ['debt.act.wizard', 'dynamic.report']

    _dr_base_name = _('Debt act')
    _report_tag = 'dynamic.da'

    @api.multi
    def name_get(self):
        res = list()
        for rec in self:
            report_name = _('Debt act')
            if rec.date_from:
                if rec.type == 'all':
                    report_name += ' {}'.format(_('from'))
                report_name += ' {}'.format(rec.date_from)
            if rec.date_to and rec.type == 'all':
                report_name += ' {} {}'.format(_('to'), rec.date_to)
            res.append((rec.id, report_name))
        return res

    filtered_partner_ids = fields.Many2many('res.partner', dynamic_report_front_filter=True)
    account_ids = fields.Many2many('account.account', dynamic_report_front_filter=True)
    show_original_amounts = fields.Boolean(dynamic_report_front_filter=True)
    dont_show_zero_values = fields.Boolean(dynamic_report_front_filter=True)
    dont_show_zero_debts = fields.Boolean(dynamic_report_front_filter=True)
    date_range = fields.Selection(default='last_financial_year')

    @api.multi
    def get_report_data(self):
        self.ensure_one()
        if not self.env.user.has_group('robo_basic.group_robo_premium_manager'):
            raise exceptions.UserError(_('Only the manager can view this report'))
        write_values = dict()
        # Adjust display partner selection that is not really necessary but report data still checks it
        write_values['all_partners'] = not self.filtered_partner_ids
        self.write(write_values)
        return super(AccReportGeneralLedgerSL, self).get_report_data()

    @api.multi
    def _get_report_data(self):
        self.ensure_one()
        self = self._update_self_with_report_language()
        res = []
        data = self.get_data()
        ReportObj = self.env['report.skolu_suderinimas.report_aktas_multi']
        report_data = ReportObj.get_report_data(data)
        partner_data = report_data[0] if isinstance(report_data, (list, tuple, set)) and len(report_data) > 1 else {}

        keys_with_currencies = ['orig_amount', 'credit', 'debit', 'balance']

        group_partner_lines = self.detail_level == 'sum'

        for partner_id, currency_data in iteritems(partner_data):
            partner = self.env['res.partner'].browse(partner_id)
            if self.dont_show_zero_debts:
                if all(tools.float_is_zero(
                        currency_data[currency]['debit'] - currency_data[currency]['credit'],
                        precision_digits=2
                ) for currency in currency_data.keys()):
                    continue
            if self.dont_show_zero_values:
                credit_debit_value = 0
                for currency in currency_data:
                    credit_debit_value += currency_data[currency]['credit']
                    credit_debit_value -= currency_data[currency]['debit']
                if tools.float_is_zero(credit_debit_value, precision_digits=2):
                    continue
            for currency_id, data in iteritems(currency_data):
                partner_balance_line = {
                    'partner_id': {'value': partner_id, 'display_value': partner.name or partner.display_name},
                    'balance': {'value': 0.0, 'currency_id': currency_id}
                }
                for line in data.get('lines', list()):
                    record_model, record_id = line.get('record_model'), line.get('record_id')
                    # Add balance
                    balance = line.get('debit', 0.0) - line.get('credit')
                    if group_partner_lines:
                        # Lines are grouped, only the partner and balance is shown. Update balance and continue
                        partner_balance_line['balance']['value'] += balance
                        continue
                    line['balance'] = balance

                    # Convert values
                    for key, value in iteritems(line):
                        value = value.id if isinstance(value, models.BaseModel) else value  # Convert object to its id

                        key_values = {'value': value}

                        # Set currency for column data if necessary
                        set_currency = key in keys_with_currencies
                        if set_currency:
                            key_values['currency_id'] = currency_id

                        line[key] = key_values

                    # Add partner to line values.
                    line['partner_id'] = {'value': partner_id, 'display_value': partner.name or partner.display_name}

                    # Get doc type from partner and set it as line doc type name
                    doc_type = line.get('doc_type', {}).get('value')
                    doc_type_name = partner.get_doc_type(doc_type)
                    line['doc_type'] = {
                        'value': doc_type or 'other',
                        'display_value': doc_type_name
                    }

                    if record_model and record_id:
                        line['__record_data__'] = {
                            'record_model': record_model,
                            'record_ids': [record_id]
                        }
                    res.append(line)  # Add line as object to show
                if group_partner_lines:
                    res.append(partner_balance_line)
        return res

    @api.multi
    def get_report_column_data(self):
        """
        Extend the parent method that returns column data to show only applicable columns for each report type.
        """
        self.ensure_one()
        res = super(AccReportGeneralLedgerSL, self).get_report_column_data()

        force_hidden_columns = []
        # Hide partner column if type is report is grouped by partner
        if self.detail_level == 'detail' and 'partner_id' in self.group_by_field_ids.mapped('identifier'):
            force_hidden_columns.append('partner_id')

        res = [column for column in res if column.get('identifier') not in force_hidden_columns]

        if self.detail_level == 'sum':
            # Only show partner and balance columns
            res = [column for column in res if column.get('identifier') in ['partner_id', 'balance']]

        return res

    @api.multi
    def _get_dynamic_report_front_filter_fields(self):
        self.ensure_one()
        res = super(AccReportGeneralLedgerSL, self)._get_dynamic_report_front_filter_fields()
        shown_filter_identifiers = ['result_selection', 'account_ids', 'date_from', 'filtered_partner_ids',
                                    'show_original_amounts', 'dont_show_zero_values', 'dont_show_zero_debts']
        if self.type == 'all':
            shown_filter_identifiers += ['date_to']
        res = [x for x in res if x in shown_filter_identifiers]
        return res

    @api.multi
    def get_enabled_group_by_data(self, skip_stored_sorting=False):
        self.ensure_one()
        if self.detail_level == 'sum':
            return []  # Disable grouping since only partner and balance is shown
        return super(AccReportGeneralLedgerSL, self).get_enabled_group_by_data(skip_stored_sorting=skip_stored_sorting)

    @api.multi
    def get_report_field_name(self, field):
        self.ensure_one()
        if self.type != 'all' and field.name == 'date_from':
            return _('Debts for date')
        return super(AccReportGeneralLedgerSL, self).get_report_field_name(field)

    @api.multi
    def get_debt_act_wizard_values(self):
        self.ensure_one()
        vals = {
            'report_type': 'debt_act',
            'report_language': self.report_language,
            'type': self.type,
            'detail_level': self.detail_level,
            'date': self.date,
            'date_from': self.date if self.type == 'unreconciled' else self.date_from,
            'date_to': self.date_to,
            'date_range': self.date_range,
            'account_type_filter': self.account_type_filter,
            'partner_ids': [(6, 0, self.filtered_partner_ids.ids)],
            'account_ids': [(6, 0, self.account_ids.ids)] if self.account_ids else False,
            'show_original_amounts': self.show_original_amounts,
            'show_accounts': self.show_accounts,
            'dont_show_zero_values': self.dont_show_zero_values,
            'dont_show_zero_debts': self.dont_show_zero_debts,
        }
        return vals

    @api.multi
    def _create_debt_act_wizard(self):
        self.ensure_one()
        vals = self.get_debt_act_wizard_values()
        lang = self.report_language or self.env.user.lang or 'lt_LT'
        wiz_id = self.env['debt.act.wizard'].with_context(lang=lang).create(vals)
        return wiz_id
