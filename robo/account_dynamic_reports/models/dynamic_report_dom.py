
from odoo import models, api
from odoo.addons.account_dynamic_reports.models.dynamic_report_dom_group import DynamicReportDOMGroup
from odoo.addons.account_dynamic_reports.tools.format_tools import format_number_with_currency
from odoo.addons.account_dynamic_reports.models.dynamic_report_dom_element import RECORD_DATA_KEY


def get_report_item_model(item):
    return item.get(RECORD_DATA_KEY, {}).get('record_model')


def filter_shown_columns(columns):
    shown_columns = [col for col in columns if col.get('shown')]
    if not shown_columns:
        shown_columns = [col for col in columns if col.get('shown_by_default')]
    return shown_columns


def process_sorting_data(columns_to_render, sorting_data=None):
    """
    Processes the sorting identifiers into columns
    @param columns_to_render: (dict) Columns that are rendered on the report
    @param sorting_data: (dict) Data to sort by
    @return: (dict) data to sort by
    """
    res = []

    shown_columns = filter_shown_columns(columns_to_render)

    if not sorting_data:
        # If no sorting data is set - find sequence column and sort by it
        sequence_column = [col for col in columns_to_render if col.get('identifier') == 'sequence']
        if sequence_column:
            res.append({'sorting_column': sequence_column[0], 'direction': 'ascending'})
        elif shown_columns:  # Or use the first shown column
            res.append({'sorting_column': shown_columns[0], 'direction': 'ascending'})
        elif columns_to_render:  # Or use the first column
            res.append({'sorting_column': columns_to_render[0], 'direction': 'ascending'})

    for column_identifiers_to_sort_by_data in sorting_data:
        sorting_direction = column_identifiers_to_sort_by_data.get('direction', 'ascending') or 'ascending'
        sorting_column_identifier = column_identifiers_to_sort_by_data.get('field')

        # If the sorting column identifier could not be determined - add the first column as the column to sort by
        if not sorting_column_identifier:
            if shown_columns:
                res.append({'sorting_column': shown_columns[0], 'direction': sorting_direction})
            elif columns_to_render:
                res.append({'sorting_column': columns_to_render[0], 'direction': sorting_direction})
            continue

        identified_columns = [col for col in columns_to_render if col.get('identifier') == sorting_column_identifier]
        if identified_columns:
            sorting_column = identified_columns[0]
            res.append({'sorting_column': sorting_column, 'direction': sorting_direction})
    return res


class DynamicReportDOM(models.AbstractModel):
    _name = 'dynamic.report.dom'

    @api.model
    def _get_all_actions_for_models(self, record_models):
        """
        Gets all actions for the provided record models
        :return: Actions for given models
        :rtype IrActionsActWindow
        :type record_models: list(str)
        """
        user = self.env.user
        return self.env['ir.actions.act_window'].sudo().search([
            ('robo_front', '=', True),
            ('res_model', 'in', record_models)
        ]).filtered(lambda action: not action.groups_id or any(user.has_group(group) for group in action.groups_id))

    @api.model
    def _get_model_actions_from_data(self, data):
        """
        Gets model actions based on record models for the provided data
        :type data: list(dict(dict()))
        :rtype IrActionsActWindow
        :return: ir.actions.act_window
        """
        data_models = list(set(get_report_item_model(x) for x in data))
        return self._get_all_actions_for_models(data_models)

    @api.model
    def update_data_with_actions(self, data):
        """ Updates provided data with missing actions """
        actions = self._get_model_actions_from_data(data)
        for rec in data:
            object_record_data = rec.get(RECORD_DATA_KEY)
            if not object_record_data:
                continue  # Object has no info about any record, must be a manually generated dict entry

            if object_record_data.get('action_id'):
                continue

            # Find the action based on the record model
            record_model = object_record_data.get('record_model')
            record_model_actions = actions.filtered(lambda action: action.res_model == record_model)
            if not record_model_actions:
                continue

            if len(record_model_actions) > 1:
                # Prefer tree action over others. All actions should already have robo_front
                tree_actions = record_model_actions.filtered(
                    lambda action: any('tree' in action_view_mode for action_view_mode in action.view_mode.split(','))
                )
                if tree_actions:
                    record_model_actions = tree_actions

            object_record_data['action_id'] = record_model_actions[0].id

    @api.model
    def format_number_with_currency(self, number, currency_id, language='lt_LT'):
        currency = currency_id and self.env['res.currency'].browse(currency_id).exists()
        if not currency:
            return number
        language = self.env['res.lang']._lang_get(language)
        return format_number_with_currency(number, currency, language)

    @api.model
    def create_dynamic_report_dom_from_data(self, data, language, group_by=None):
        """
        Creates the dynamic report object DOM to differentiate between grouped data later
        @param data: (list) report data to group
        @param group_by: (list) fields to group by
        @param language: (str) language code
        :return: (dict) grouped data

        """
        self.ensure_one()

        data = data or list()

        self.update_data_with_actions(data)  # Find actions and add them to each data row

        # Create a root group
        root_group = DynamicReportDOMGroup(language=language, currency_format_function=self.format_number_with_currency,
                                           level=-1, group_id=0)
        root_group.add_children(data)  # Add the data as children of the root group

        self.group_groups_child_data(root_group, group_by)

        return root_group

    @api.model
    def group_groups_child_data(self, group_to_group, fields_to_group_by):
        # If there's nothing to group by - just return the root group
        if not group_to_group or not fields_to_group_by:
            return

        groups_to_group = [group_to_group]

        # Loop through fields to group by
        for field_to_group_by in fields_to_group_by:
            for group in groups_to_group:
                group.group_children(field_to_group_by)

            # Determine which groups to group next (child groups of current groups)
            new_groups_to_group = list()
            for group in groups_to_group:
                new_groups_to_group += group.subgroups
            groups_to_group = new_groups_to_group

    @api.model
    def get_render_data(self, group, column_render_data, sorting_data=None):
        """
        Gets all the necessary data to render the provided group in a table
        @param group: Group to render
        @param column_render_data: (list) of dicts for columns to render
        @param sorting_data: (dict) how to sort the data
        @return: (dict) render data
        """
        if not isinstance(group, DynamicReportDOMGroup):
            return

        sorting_data = process_sorting_data(column_render_data, sorting_data)

        # Determine which columns are actually shown on the report
        columns_to_show = filter_shown_columns(column_render_data)

        # Treats group as base group
        render_data = group.get_full_render_data(columns_to_show, sorting_data=sorting_data)

        render_data.update({'column_data': columns_to_show})

        return render_data
