# -*- coding: utf-8 -*-
import time

from odoo import tools, _
from odoo.addons.account_dynamic_reports.models.dynamic_report_dom_element import DynamicReportDOMElement

DEFAULT_REPORT_GROUP_TEMPLATE = 'account_dynamic_reports.DynamicReportPDFGroupTitleRow'
PREFERRED_GROUP_TITLE_COLUMN_SPAN = 3


class DynamicReportDOMGroup(object):
    def __init__(self, name='', level=0, language=None, currency_format_function=None, template=None, group_id=None,
                 group_by_identifier=None):
        self.name = name
        self.group_by_identifier = group_by_identifier
        self.parent = None
        self.subgroups = list()
        self.children = list()
        self.level = level
        self.language = language or (self.parent.language if self.parent else None)
        self.currency_format_function = currency_format_function
        self.template = template or DEFAULT_REPORT_GROUP_TEMPLATE

        # Group identifier to determine child elements in JS. Should be unique between child and parent subgroups.
        self.group_id = group_id

    def add_child(self, obj):
        """
        Adds child to group
        @param obj: (DynamicReportDOMElement) Child to add
        """
        if not isinstance(obj, DynamicReportDOMElement) and isinstance(obj, dict):
            obj = DynamicReportDOMElement(data=obj)
        self.children.append(obj)
        obj.parent = self
        if not obj.level:
            obj.level = max(self.level + 1, obj.level)
        obj.group_id = self.group_id

    def add_children(self, objects):
        """
        Adds children to group
        @param objects: (DynamicReportDOMElement) Children to add
        """
        for obj in objects:
            self.add_child(obj)

    def remove_children(self, children):
        """
        Removes child elements from group
        @param children: (DynamicReportDOMElement) Children to remove
        """
        child_elements_to_remove = [child for child in children if child in self.children]
        self.children = [child for child in self.children if child not in child_elements_to_remove]
        for child_element_to_remove in child_elements_to_remove:
            child_element_to_remove.parent = False

    def add_subgroup(self, obj, force_same_level=False):
        """
        Adds subgroup to group
        @param obj: (DynamicReportDOMGroup) Group to add
        @param force_same_level: (bool) Should the subgroup have the same level as the parent group
        """
        self.subgroups.append(obj)
        obj.parent = self
        obj.level = self.level if force_same_level else (obj.level or self.level + 1)

        obj.group_id = self.get_next_subgroup_id()

    def get_next_subgroup_id(self):
        existing_subgroup_ids = [subgroup.group_id for subgroup in self.subgroups]
        max_group_id = max(existing_subgroup_ids) if existing_subgroup_ids else 0
        return max_group_id + 1

    def get_render_settings(self):
        """
        Returns the render settings
        @return: (dict) render settings
        """
        render_data = {'template_id': self.template}
        return render_data

    def get_full_data(self):
        """
        Gets full data of the group.
        @return: (dict) data
        """
        # Only return the data that exists
        data = dict()
        if self.name:
            data['name'] = self.name
        if self.subgroups:
            data['subgroups'] = [group.get_full_data() for group in self.subgroups]
        if self.children:
            data['children'] = [child.get_data() for child in self.children]
        action_data = self.get_action_data()
        if action_data:
            data['action_data'] = action_data
        if data:
            data['level'] = self.level
        render_data = self.get_render_settings()
        data.update(render_data)  # Update data with render data
        return data

    def get_action_data(self):
        """
        Gets action data for each child of the group
        @return: (dict) list of group actions and records for each action
        """
        action_data = list()
        if not self.children:
            return action_data

        # Get all actions for each child
        action_ids = [child.action for child in self.children if child.action]
        if not action_ids:
            return action_data

        for action_id in set(action_ids):
            # Find children by action
            children_by_action = [child for child in self.children if action_id == child.action]

            # Find child records
            child_record_ids = []
            for child in children_by_action:
                if child.record_ids:
                    child_record_ids += child.record_ids
            if not child_record_ids:
                continue

            action_data.append({'action_id': action_id, 'record_ids': child_record_ids})
        return action_data

    def get_child_values_by_field(self, field):
        """
        Gets child values by field
        @param field: child data key to get the values of
        @return: (dict) values of the field for each child
        """
        # Get the values of the field for each child
        values_by_field = list(set([child.data.get(field, {}).get('value') for child in self.children]))

        value_name_map = dict()  # Start building a value name map

        name_fields = ['name', 'display_value', 'value']  # Which data dict keys can be used to display the value name

        for child_field_value in values_by_field:
            if not child_field_value:
                # No field value, meaning that some entries have undefined values
                value_name_map[child_field_value] = _("Undefined")
                continue

            # Find child elements with the value
            child_elements_with_value = [
                child for child in self.children
                if child.data.get(field, {}).get('value') == child_field_value
            ]

            # Try to find a display value for the value/group
            value_name = None
            for name_field in name_fields:
                for child in child_elements_with_value:
                    value_name = child.data.get(field).get(name_field)
                    if value_name:
                        break
                if value_name:
                    break
            if not value_name:
                value_name = _("Undefined")

            value_name_map[child_field_value] = value_name

        return value_name_map

    def group_children(self, field_to_group_by):
        """
        Groups children of group into subgroup
        @param field_to_group_by: (str) field to group by
        """
        # Get list of values by the field for each child
        value_name_map_for_field = self.get_child_values_by_field(field_to_group_by)

        # Convert value name map to list
        value_name_list = value_name_map_for_field.items()
        # Sort value name list by value name and move the "Undefined" (value=False) entries to the bottom.
        value_name_list.sort(key=lambda vnm: (not vnm[0], vnm[1]))

        # Loop through each value for the field to group by and create a new group
        for field_value, field_name in value_name_list:
            children_by_value = [
                child for child in self.children
                if child.data.get(field_to_group_by, {}).get('value') == field_value
            ]
            if not children_by_value:
                continue  # Don't create an empty group

            # Remove the grouped children from the current group
            self.remove_children(children_by_value)

            # Create a new group node
            child_group = DynamicReportDOMGroup(
                name=field_name, level=self.level+1, language=self.language,
                currency_format_function=self.currency_format_function, group_id=self.get_next_subgroup_id(),
                group_by_identifier=field_to_group_by
            )
            child_group.add_children(children_by_value)

            # Add the newly created group node as a child group
            self.add_subgroup(child_group)

    def get_total_number_of_subgroups(self):
        """
        Calculates how many total subgroups there are
        @return: (int) number of subgroups
        """
        res = len(self.subgroups)
        for subgroup in self.subgroups:
            res += subgroup.get_total_number_of_subgroups()
        return res

    def get_column_subtotal(self, column):
        """
        Calculates subtotal for the given column by calculating the values for each child element for each subgroup
        @param column: (dict) column data
        @return: (float) column subtotal
        """
        subtotal = 0.0
        for subgroup in self.subgroups:
            subtotal += subgroup.get_column_subtotal(column)
        for child_element in self.children:
            subtotal += child_element.get_column_number_value(column) or 0.0
        return subtotal

    def get_complete_list_of_children(self):
        list_of_child_elements = list()
        for subgroup in self.subgroups:
            list_of_child_elements += subgroup.get_complete_list_of_children()
        list_of_child_elements += self.children
        return list_of_child_elements

    def determine_currency_id_from_child_data(self, column_identifier):
        """
        Check all group child elements to determine which currency id should be used
        @param column_identifier: (str) the column identifier to look for the currency in child data
        @return: (int) or None - currency object id
        """
        all_child_elements = self.get_complete_list_of_children()
        child_data = [child.get_data() for child in all_child_elements]
        if not child_data or not column_identifier:
            return
        currencies = [x.get(column_identifier, dict()).get('currency_id') for x in child_data]
        currencies = list(set([currency for currency in currencies if currency or isinstance(currency, int)]))
        currency_id = currencies[0] if currencies and all(x == currencies[0] for x in currencies) else None
        return currency_id

    def any_child_has_child_elements(self):
        for child in self.children:
            if child.children:
                return True
        for subgroup in self.subgroups:
            if subgroup.any_child_has_child_elements():
                return True
        return False

    def find_maximum_inner_group_level(self):
        maximum_level = self.level
        for child in self.children:
            maximum_level = max(child.level, maximum_level)
        for subgroup in self.subgroups:
            maximum_level = max(subgroup.find_maximum_inner_group_level(), maximum_level)
        return maximum_level

    def get_full_render_data(self, columns_to_render, include_subgroups=True, sorting_data=None):
        """
        Gets full render data of the group
        @param columns_to_render: (list) of dicts containing data of the columns to render
        @param include_subgroups: (bool) should subgroups be included
        @param sorting_data: (dict) sorting data to sort the child elements by
        @return: (dict) full render data including the data of how to render subgroups and child elements
        """
        # Get data of how to render group title row
        group_render_data = self._get_render_data(columns_to_render)

        # Sort child elements
        child_elements = self.get_sorted_child_elements(sorting_data)

        # Get child element render data
        child_element_render_data = list()
        for child_element in child_elements:
            child_element_render_data.append(child_element.get_render_data(columns_to_render))
        group_render_data['children'] = child_element_render_data

        # Get subgroup render data
        group_render_data['subgroups'] = [
            subgroup.get_full_render_data(columns_to_render, include_subgroups, sorting_data)
            for subgroup in self.subgroups if include_subgroups
        ]

        return group_render_data

    def _get_render_data(self, columns_to_render):
        """
        Gets data of how the group title should be rendered
        @param columns_to_render: (list) dictionaries containing column info of which columns should be shown/rendered
        the number of columns to add before based on this groups level
        @return: (dict) Info of how the group should be rendered, including the name and the subtotals for each column
        """
        group_title = self.name
        number_of_columns_to_show = len(columns_to_render)
        group_title_column_span = min(number_of_columns_to_show, PREFERRED_GROUP_TITLE_COLUMN_SPAN)

        # Determine which is the first column totals are being calculated for
        columns_to_calculate_totals_for = [col.get('calculate_totals') for col in columns_to_render]
        if True in columns_to_calculate_totals_for:
            first_column_to_calculate_totals_for = columns_to_calculate_totals_for.index(True)
        else:
            first_column_to_calculate_totals_for = number_of_columns_to_show-1

        # Determine if the group title should span two rows
        show_two_rows = (first_column_to_calculate_totals_for <= group_title_column_span) and group_title

        # Don't show two rows if there's a small number of columns and the first column to calculate totals for is in
        # the second half of the columns. Column titles should fit.
        if show_two_rows and number_of_columns_to_show <= 4 and \
                first_column_to_calculate_totals_for > number_of_columns_to_show // 2:
            show_two_rows = False
            group_title_column_span = min(group_title_column_span, first_column_to_calculate_totals_for)

        if not show_two_rows:
            # The maximum column span for group title is up until the first column where totals have to be calculated
            group_title_column_span = max(group_title_column_span, first_column_to_calculate_totals_for)
        else:
            group_title_column_span = len(columns_to_render)

        group_total_data = list()
        first_shown_reached = False
        for column_index, column in enumerate(columns_to_render):
            # Get column info
            identifier = column.get('identifier')
            column_span = column.get('colspan', 1)
            calculate_totals = column.get('calculate_totals', False)
            is_number = column.get('is_number')

            # Create empty group column data based on column
            group_column_data = {'colspan': column_span, 'show_total': calculate_totals, 'total': 0.0}

            # The totals of the column should not be shown
            if not is_number or not calculate_totals:
                if first_shown_reached:
                    group_total_data.append(group_column_data)
                continue

            first_shown_reached = True  # Used for showing totals when the group title is rendered in a single row.

            # Get the subtotal of all of the groups and child elements belonging to this group for the column
            total_value = self.get_column_subtotal(column)

            # Determine currency id
            currency_id = column.get('currency_id')
            if not currency_id:
                currency_id = self.determine_currency_id_from_child_data(identifier)
                if currency_id:
                    column['currency_id'] = currency_id

            if currency_id:
                # Format based on currency
                total_value = self.currency_format_function(total_value, currency_id, self.language)
            else:
                # Round as a simple number
                total_value = tools.float_round(total_value, column.get('precision_digits', 2))

            # Update the column data with the total
            group_column_data['total'] = total_value
            # Append the data to the totals data of the group
            group_total_data.append(group_column_data)

        render_data = {
            'two_rows': show_two_rows,
            'group_title': group_title,
            'group_title_colspan': group_title_column_span,
            'group_totals': group_total_data,
            'first_totals_colspan': first_column_to_calculate_totals_for,
            'number_of_columns': len(columns_to_render),
            'any_child_has_child_elements': self.any_child_has_child_elements(),
            'max_group_level': self.find_maximum_inner_group_level(),
            'group_id': self.get_full_group_id(),
            'group_by_identifier': self.group_by_identifier,
            'group_level': self.level,
            'is_totals': self.level == -1
        }
        render_settings = self.get_render_settings()
        render_data.update(render_settings)
        return render_data

    def get_full_group_id(self):
        return str(self.level) + str(self.group_id)

    def get_sorted_child_elements(self, sorting_data):
        """
        Sort child elements and return them in a list
        @param sorting_data: (list) of dicts containing sorting data [{'sorting_column': (dict), 'direction': (str)}]
        @return: (list) Child elements sorted by column and direction
        """
        child_elements = [child_element for child_element in self.children]

        reverse = False  # Only allow reverse sorting if there's a single sort by row and the descending direction is
        # specified
        if len(sorting_data) == 1:
            reverse = sorting_data[0].get('direction') == 'descending'

        # Read the identifiers to sort by
        sorting_columns = []
        for sorting_data_row in sorting_data:
            sorting_column = sorting_data_row.get('sorting_column', {})
            if not sorting_column:
                continue
            sorting_columns.append(sorting_column)

        if not sorting_columns:
            return child_elements

        # Sort based on the number value or the display value
        child_elements.sort(
            key=lambda x: [
                (x.get_column_number_value(column) or x.determine_column_display_value(column))
                for column in sorting_columns
            ], reverse=reverse
        )
        return child_elements

