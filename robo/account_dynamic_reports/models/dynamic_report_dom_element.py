# -*- coding: utf-8 -*-
from odoo import tools

DEFAULT_REPORT_ELEMENT_TEMPLATE = 'account_dynamic_reports.DynamicReportPDFGroupDataRow'
NO_WRAP_STYLE = 'white-space: nowrap !important; word-break: keep-all !important'
NUMBER_TYPES = (int, float, long)
RECORD_DATA_KEY = '__record_data__'


class DynamicReportDOMElement(object):
    def __init__(self, identifier=None, data=None, level=0, template=None):
        self.identifier = identifier
        self.data = data or dict()

        record_data = self.data.get(RECORD_DATA_KEY, dict())
        self.record_ids = record_data.get('record_ids')
        self.record_model = record_data.get('record_model')
        self.action = record_data.get('action_id')
        self.template = template or DEFAULT_REPORT_ELEMENT_TEMPLATE

        self.parent = None
        self.children = list()
        self.level = self.data.get('level', {}).get('value') or level

    def get_data(self):
        data = self.data or dict()
        if data:
            data['level'] = self.level
        return data

    def get_render_settings(self):
        render_data = {'template_id': self.template}
        return render_data

    def get_full_data(self):
        data = self.get_data()
        render_settings = self.get_render_settings()
        data.update(render_settings)
        return data

    def get_column_number_value(self, column):
        """
        Determines which one of the data values should be used for the column as the number value
        @param column: (dict) column info
        @return: float or None - the float value for the column
        """
        column_identifier = column.get('identifier')
        number_value = None
        if not column_identifier:
            return number_value

        is_number = column.get('is_number')
        if not is_number:
            return number_value

        cell_data = self.data.get(column_identifier, dict())
        if not cell_data:
            return number_value

        cell_display_value = cell_data.get('display_value')
        cell_process_value = cell_data.get('value')
        if isinstance(cell_display_value, NUMBER_TYPES):
            number_value = cell_display_value
        elif isinstance(cell_process_value, NUMBER_TYPES):
            number_value = cell_process_value

        return number_value

    def determine_column_display_value(self, column, cell_data=None):
        """
        Determines the display value for the element for the provided column
        @param column: (dict) column data
        @param cell_data: (dict) data of this object for the column
        @return:
        """
        if not cell_data:
            column_identifier = column.get('identifier')
            if not column_identifier:
                return None
            cell_data = self.data.get(column_identifier, dict())

        # Get the display value
        cell_display_value = cell_data.get('display_value')
        cell_process_value = cell_data.get('value')
        cell_display_value = cell_display_value or cell_process_value
        if not cell_display_value and not isinstance(cell_display_value, NUMBER_TYPES):
            cell_display_value = ''

        cell_number_value = self.get_column_number_value(column)  # Get the number value

        is_number = column.get('is_number')

        # Adjust display data based on number properties
        if not is_number or (not cell_number_value and not isinstance(cell_number_value, NUMBER_TYPES)):
            return cell_display_value

        # Determine display currency
        currency_id = cell_data.get('currency_id')
        if not currency_id:
            cell_data['currency_id'] = currency_id = column.get('currency_id')
        display_currency_id = cell_data.get('display_currency_id') or currency_id

        if display_currency_id and self.parent and self.parent.currency_format_function:
            cell_display_value = self.parent.currency_format_function(cell_number_value, display_currency_id,
                                                                      self.parent.language)
        else:
            cell_display_value = tools.float_round(cell_number_value, column.get('precision_digits') or 2)
        return cell_display_value

    def get_column_render_data(self, column):
        """
        Computes data to be shown in the column
        @param column: (dict) column data
        @return: (dict) data of the element for the column
        """
        # Create empty cell object
        cell_object = {'value': '', 'is_number': False, 'bold': False, 'custom_css': '', 'colspan': 1}
        column_identifier = column.get('identifier')
        if not column_identifier:
            return cell_object

        is_possibly_a_date_field = 'date' in column_identifier
        is_number = column.get('is_number')

        cell_data = self.data.get(column_identifier, dict())  # Get data for column/cell
        column_span = cell_data.get('colspan', 1)

        # Update cell value with column properties
        cell_object['colspan'] = column_span
        cell_object['is_number'] = is_number

        # Append empty cell object
        if not cell_data:
            return cell_object

        cell_display_value = self.determine_column_display_value(column, cell_data)

        column_style_attributes = column.get('style_attributes', dict())
        custom_css = NO_WRAP_STYLE if is_number or is_possibly_a_date_field else ''
        cell_object = {
            'value': cell_display_value,
            'is_number': is_number,
            'bold': column_style_attributes.get('bold', False),
            'custom_css': custom_css,
            'colspan': column_span
        }
        return cell_object

    def get_render_data(self, columns_to_render):
        """
        Gets the data how the element should be rendered
        @param columns_to_render: (list) of dicts of which columns are going to be rendered
        @return: (dict) element render data
        """
        cells = list()

        for column in columns_to_render:
            cells.append(self.get_column_render_data(column))

        render_data = {
            'cells': cells,
            'action_id': self.action,
            'record_ids': self.record_ids,
            'record_model': self.record_model,
            'child_elements': self.children,
            'indentation_level': self.level,
            'max_group_level': self.parent.find_maximum_inner_group_level(),
            'group_id': self.parent and self.parent.get_full_group_id(),
            'data': self.data
        }
        render_settings = self.get_render_settings()
        render_data.update(render_settings)
        return render_data
