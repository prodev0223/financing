# -*- coding: utf-8 -*-

from six import iteritems
from odoo import api, fields, models, _
from odoo.addons.account_dynamic_reports.tools.date_tools import get_date_range_selection_from_selection

# This name defines the field boolean report filters should display under. Used in js widget.
BOOLEAN_FIELD_NAME = 'other_filters'


class DynamicReportFilters(models.AbstractModel):
    _name = 'dynamic.report.filters'

    @api.model
    def _default_journal_ids(self):
        """
            Return all account journals, including inactive ones, since valid account move lines can exist with
            archived journal
        """
        return self.env['account.journal'].with_context(active_test=False).search([])

    @api.onchange('date_range')
    def onchange_date_range(self):
        if self.date_range:
            company = self.env.user.company_id
            self.date_from, self.date_to = get_date_range_selection_from_selection(
                self.date_range, company.fiscalyear_last_day, company.fiscalyear_last_month
            )

    @api.onchange('date_from', 'date_to')
    def onchange_dates(self):
        self.date_range = self.get_date_range_from_dates(self.date_from, self.date_to)

    journal_ids = fields.Many2many('account.journal', string='Journals', required=True, default=_default_journal_ids)

    analytic_ids = fields.Many2many('account.analytic.account', string='Analytic Accounts')
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Analytic Tags')

    date_range = fields.Selection([
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('this_quarter', 'This Quarter'),
        ('this_fiscal_year', 'This Fiscal Year'),
        ('yesterday', 'Yesterday'),
        ('last_week', 'Last Week'),
        ('last_month', 'Last Month'),
        ('last_quarter', 'Last Quarter'),
        ('last_financial_year', 'Last Fiscal Year')
    ], string='Date Range', default='this_fiscal_year')
    date_from = fields.Date(string='Start Date', dynamic_report_front_filter=True)
    date_to = fields.Date(string='End Date', dynamic_report_front_filter=True)

    account_ids = fields.Many2many('account.account', string='Accounts')
    account_tag_ids = fields.Many2many('account.account.tag', string='Account Tags')

    partner_ids = fields.Many2many('res.partner', string='Partners', domain=[
        ('parent_id', '=', False), '|', ('customer', '=', True), ('supplier', '=', True)
    ])

    @api.model
    def get_date_range_from_dates(self, date_from, date_to):
        """
        Gets date range based on the provided dates
        :param date_from: (str) date from
        :param date_to:  (str) date to
        :return: (str) date range (month/day/year/last week, etc.)
        """
        if not date_from or not date_to:
            return False

        company = self.env.user.company_id

        # Loop through all possible date ranges, get dates for range and compared with the ones provided.
        for date_range_selection in [x[0] for x in self._fields.get('date_range').selection]:
            range_date_from, range_date_to = get_date_range_selection_from_selection(
                date_range_selection, company.fiscalyear_last_day, company.fiscalyear_last_month
            )
            if range_date_from == date_from and range_date_to == date_to:
                return date_range_selection
        return False

    @api.multi
    def process_filters_into_write_values(self, filters):
        """ Processes provided filter values into a writeable dictionary """
        enabled_boolean_fields = filters.get(BOOLEAN_FIELD_NAME, list())  # Get the enabled boolean fields
        for enabled_boolean_field in enabled_boolean_fields:
            filters[enabled_boolean_field] = True

        values_to_write = {}

        filter_keys = filters.keys()

        if any(key in filter_keys for key in ['date_from', 'date_to']):
            values_to_write['date_range'] = False

        report_filter_fields = self._get_dynamic_report_front_filter_fields()

        for report_filter_field in report_filter_fields:
            field = self._fields.get(report_filter_field)  # Get field attributes
            field_type = field.type  # Determine field type

            new_field_values = filters.get(report_filter_field, False)
            if isinstance(new_field_values, list):
                new_field_values = list(set(new_field_values))

            if field_type in ['many2many', 'many2one']:
                vals = [(5,)]
                if new_field_values:
                    vals += [(4, x) for x in new_field_values]
                values_to_write[report_filter_field] = vals
            elif field_type == 'selection':
                selection_field_value = False
                if new_field_values and isinstance(new_field_values, list):
                    selection_field_value = new_field_values[0]
                values_to_write[report_filter_field] = selection_field_value
            else:
                values_to_write[report_filter_field] = new_field_values
        return values_to_write

    @api.multi
    def get_filters(self):
        """
        Gets possible filters
        :return: (dict) applicable filters
        """
        self.ensure_one()
        filters = dict()
        context = self._context.copy()
        if 'lang' not in context:
            context.update({'lang': self.determine_language_code()})
        filters['field_filters'] = self.with_context(context).sudo().get_filters_from_wizard_fields()
        filters['company_name'] = self.env.user.with_context(context).company_id.name
        return filters

    @api.multi
    def _get_dynamic_report_front_filter_fields(self):
        """
            Get the fields that are filters for the dynamic report (fields with the dynamic_report_front_filter
            attribute)
        """
        report_filter_fields = []
        for (key, value) in iteritems(self._fields):
            try:
                is_report_filter_field = value.dynamic_report_front_filter
            except AttributeError:
                is_report_filter_field = False
            if is_report_filter_field:
                report_filter_fields.append(key)
        return report_filter_fields

    @api.multi
    def get_filters_from_wizard_fields(self):
        """
        Builds filter data based on wizard fields. In order for a field to be filterable by on a dynamic report just add
        dynamic_report_front_filter=True to the wizard field.
        @return: dictionary of filters
        """
        self.ensure_one()
        self.onchange_date_range()

        report_filter_fields = self._get_dynamic_report_front_filter_fields()

        filters = {}
        for field_name in report_filter_fields:
            field = self._fields.get(field_name)  # Get field attributes
            field_type = field.type  # Determine field type

            field_display_name = self.get_report_field_name(field)

            default_field_values = {
                'name': field_name,
                'string': field_display_name,
                'type': field_type,
                'current_value': [],
                'list_of_values': [],
                'allow_selecting_multiple': True,
            }
            field_values = default_field_values.copy()

            # Set filter values based on each field type
            if field_type == 'selection':
                current_value = self[field_name]
                field_values['current_value'] = [current_value] if current_value else []
                field_values['list_of_values'] = field._description_selection(self.env)
                field_values['allow_selecting_multiple'] = False
            elif field_type in ['many2many', 'many2one']:
                records = self.env[field.comodel_name].search(field.domain or list())
                record_list = []
                for record in records:
                    try:
                        name = record.display_name
                    except AttributeError:
                        name = record.name
                    record_list.append((record.id, name))
                field_values['current_value'] = self[field_name].ids
                field_values['list_of_values'] = record_list
                field_values['allow_selecting_multiple'] = field_type != 'many2one'
            elif field_type == 'boolean':
                # All boolean fields go under other filters
                field_values = filters.get(BOOLEAN_FIELD_NAME, default_field_values)
                field_values['list_of_values'].append((field_name, field_display_name))
                is_selected = self[field_name]
                if is_selected:
                    field_values['current_value'].append(field_name)
                field_values['name'] = BOOLEAN_FIELD_NAME
                field_values['string'] = _('Options')
                field_name = BOOLEAN_FIELD_NAME  # Rename so that field filter attributes goes under other_filters
            else:
                # Just set the current value, don't provide a list of values
                field_values['current_value'] = self[field_name]

            filters[field_name] = field_values

        return filters

    @api.multi
    def update_report_filters(self, filters):
        """
        Updates report with specified filters and reloads the data
        :param filters: (dict) dictionary of applied filters
        """
        self.ensure_one()
        if not filters or not isinstance(filters, dict) or not self.check_access_rights('write'):
            return

        processed_filter_values = self.process_filters_into_write_values(filters)
        data_to_write = processed_filter_values
        # Data should be refreshed on the next fetch since the filters have changed
        data_to_write['refresh_data'] = True
        self.sudo().write(data_to_write)

    @api.multi
    def get_report_field_name(self, field):
        self.ensure_one()
        return field._description_string(self.env)
