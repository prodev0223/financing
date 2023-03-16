# -*- coding: utf-8 -*-

import math

from xlsxwriter.utility import xl_col_to_name

from odoo import _

try:
    from odoo.addons.report_xlsx.report.report_xlsx import ReportXlsx
    from odoo.report.report_sxw import rml_parse
except ImportError:
    ReportXlsx = object
    rml_parse = None

DEFAULT_REPORT_OPTIONS = {
    'maximum_column_width': 55,  # Maximum size for any single column
    'minimum_column_width': 15,  # Minimum size for any single column
    'char_width_ratio': 1.0,  # Number of characters will be multiplied by this value to get the size of each column
    'orientation': 'landscape',  # Report orientation (portrait/landscape)
    'minimum_row_height': 17,  # Minimum row height
    'row_height_multiplier': 14,  # Used to calculate necessary row height. Increase to have more padding for rows.
}


class DynamicXLSXReport(ReportXlsx):

    @staticmethod
    def fix_cell_formula(formula):
        """ Refactors/fixes common formula issues created during list concatination/data processing """
        formula = formula.replace('++', '+').replace('+0.0', '').replace('=+', '=').replace('=0.0+', '=')
        if formula == '=':
            formula = '=0.0'
        return formula

    def __init__(self, name, table, rml=False, parser=rml_parse, header='external', store=False, register=True):
        ReportXlsx.__init__(self, name, table, rml, parser, header, store, register)
        self.reset_init_values()

    def reset_init_values(self):
        self.report_name = _('Report')

        self.data_sheet = self.filter_sheet = None  # Two sheets to be created later

        self.row_pos = 0

        self.filters = dict()
        self.columns = list()

        # Used for grouping. -1 as start value since +1 is added for each group (0 will be base group)
        self.outline_level = -1
        self.number_of_groups = 0

        self.group_totals_formulas = list()  # Stores sum() formulas for each group. Index is the group/outline level.

        self.column_totals = list()
        self.calculate_totals = False

        self.maximum_available_title_colspan = -1  # Based on which column is the first column to calculate totals for

    def _set_report_options(self, custom_options):
        """
        Set default report options
        @param custom_options: dictionary with data that overrides default report options
        """
        report_options = DEFAULT_REPORT_OPTIONS
        report_options.update(custom_options)
        self.report_options = report_options

    def _define_formats(self, workbook):
        """ Add cell formats to specified workbook."""

        def copy_format(book, fmt):
            properties = [f[4:] for f in dir(fmt) if f[0:4] == 'set_']
            dft_fmt = book.add_format()
            return book.add_format(
                {k: v for k, v in fmt.__dict__.items() if k in properties and dft_fmt.__dict__[k] != v})

        workbook_font = 'Arial'

        base_data_format = {
            'font': workbook_font,
            'font_size': 10,
            'top': True,
            'bottom': True,
        }
        base_header_format = {
            'font': workbook_font,
            'font_size': 10,
            'top': True,
            'bottom': True,
            'bold': True,
            'bg_color': '#2980b9',
            'font_color': '#FFFFFF',
        }

        # HEADER FORMATS
        # Regular header
        self.format_header = workbook.add_format(base_header_format)
        self.format_header.set_text_wrap()
        self.format_header.set_align('vcenter')
        # With border left
        self.format_header_border_left = copy_format(workbook, self.format_header)
        self.format_header_border_left.set_left(1)
        # With border right
        self.format_header_border_right = copy_format(workbook, self.format_header)
        self.format_header_border_right.set_right(1)
        # Number header
        self.format_header_number_column = copy_format(workbook, self.format_header)
        self.format_header_number_column.set_align('right')
        # Number header with border left
        self.format_header_number_column_border_left = copy_format(workbook, self.format_header_number_column)
        self.format_header_number_column_border_left.set_left(1)
        # Number header with border right
        self.format_header_number_column_border_right = copy_format(workbook, self.format_header_number_column)
        self.format_header_number_column_border_right.set_right(1)

        # DATA FORMATS
        # Regular data
        self.regular_data_format = workbook.add_format(base_data_format)
        self.regular_data_format.set_text_wrap()
        self.regular_data_format.set_align('vcenter')
        # With border left
        self.regular_data_format_border_left = copy_format(workbook, self.regular_data_format)
        self.regular_data_format_border_left.set_left(1)
        # With border right
        self.regular_data_format_border_right = copy_format(workbook, self.regular_data_format)
        self.regular_data_format_border_right.set_right(1)
        # Number
        self.regular_number_format = copy_format(workbook, self.regular_data_format)
        self.regular_number_format.set_num_format(self._get_number_format())
        # Number with border left
        self.regular_number_format_border_left = copy_format(workbook, self.regular_number_format)
        self.regular_number_format_border_left.set_left(1)
        # Number with border right
        self.regular_number_format_border_right = copy_format(workbook, self.regular_number_format)
        self.regular_number_format_border_right.set_right(1)

        # LINE TOTAL FORMAT
        self.line_total_format = copy_format(workbook, self.format_header_number_column)
        # With border left
        self.line_total_format_border_left = copy_format(workbook, self.line_total_format)
        self.line_total_format_border_left.set_left(1)
        # With border right
        self.line_total_format_border_right = copy_format(workbook, self.line_total_format)
        self.line_total_format_border_right.set_right(1)

        # Text align left format
        self.line_total_left_format = copy_format(workbook, self.line_total_format)
        self.line_total_left_format.set_align('left')
        # With border left
        self.line_total_left_format_border_left = copy_format(workbook, self.line_total_left_format)
        self.line_total_left_format_border_left.set_left(1)
        # With border right
        self.line_total_left_format_border_right = copy_format(workbook, self.line_total_format)
        self.line_total_left_format_border_right.set_right(1)

    def _get_desired_cell_format(self, column=1, is_header=False, is_number=False, is_totals=False, sheet=1):
        """
        Gets the cell format based on the cell and its properties
        @param column: Column to get format for (default is 1 to get for regular/middle cell with no borders)
        @param is_header: Is the data header data
        @param is_number: Is the cell data a number
        @param is_totals: Is the cell data a totals row
        @param sheet: Which sheet is it (by design only supports 2). Based on value column number is determined
        @return: Workbook format that should be used
        """
        if is_header:
            row_type = 'header'
        elif is_totals:
            row_type = 'totals'
        else:
            row_type = 'data'

        if column == 0:
            column = 'first_column'
        elif column == (len(self.filters.keys()) - 1 if sheet == 2 else len(self.columns) - 1):
            column = 'last_column'
        else:
            column = 'middle_column'

        cell_type = 'number' if is_number else 'text'

        format_map = {
            'header': {
                'first_column': {
                    'number': self.format_header_number_column_border_left,
                    'text': self.format_header_border_left,
                },
                'middle_column': {
                    'number': self.format_header_number_column,
                    'text': self.format_header,
                },
                'last_column': {
                    'number': self.format_header_number_column_border_right,
                    'text': self.format_header_border_right,
                },
            },
            'data': {
                'first_column': {
                    'number': self.regular_number_format_border_left,
                    'text': self.regular_data_format_border_left,
                },
                'middle_column': {
                    'number': self.regular_number_format,
                    'text': self.regular_data_format,
                },
                'last_column': {
                    'number': self.regular_number_format_border_right,
                    'text': self.regular_data_format_border_right,
                },
            },
            'totals': {
                'first_column': {
                    'number': self.line_total_format_border_left,
                    'text': self.line_total_left_format_border_left,
                },
                'middle_column': {
                    'number': self.line_total_format,
                    'text': self.line_total_left_format,
                },
                'last_column': {
                    'number': self.line_total_format_border_right,
                    'text': self.line_total_left_format_border_right,
                },
            },
        }

        return format_map[row_type][column][cell_type]

    def _get_number_format(self, currency_id=None):
        """
        Gets number format (based on the currency if provided)
        @param currency_id: (int) res.currency id
        @return: (string) number format
        """
        currency = currency_id and self.env['res.currency'].browse(currency_id).exists()
        default_currency_format = '#,##0.00'
        if not currency:
            return default_currency_format
        return currency.excel_format or default_currency_format

    def adjust_number_format(self, fmt, currency_id):
        """
        Adjusts the number format based on the currency
        @param fmt: sheet format to adjust
        @param currency_id: (int) res.currency id
        """
        number_format = self._get_number_format(currency_id)
        fmt.set_num_format(number_format)

    def _get_column_size_based_on_text(self, list_of_column_values):
        """
        Computes the column size based on values of that column
        @param list_of_column_values: (list) values that are going to be in the column
        @return: (float) column size
        """
        minimum_column_width = self.report_options['minimum_column_width']
        maximum_column_width = self.report_options['maximum_column_width']
        char_width_ratio = self.report_options['char_width_ratio']

        maximum_string_length = max([len(str(d)) for d in list_of_column_values]) if list_of_column_values else 0
        required_size = max(minimum_column_width, maximum_string_length) * char_width_ratio
        available_size = min(required_size, maximum_column_width)

        return available_size

    def set_up_columns(self, data):
        """
        Sets up the columns for the report. Sets the column width as well as the titles for each column. Calculates
        width based on the length of data for each column.
        @param data: (list) list of dictionary objects containing the data
        """

        required_row_height = self.report_options['minimum_row_height']

        for column_index, column in enumerate(self.columns):

            # Get column data
            column_id = column.get('identifier')
            column_name = column.get('name', '')
            currency_id = column.get('currency_id')
            is_number = column.get('is_number')
            if not column_id:
                continue
            calculate_column_totals = column.get('calculate_totals')
            if not self.calculate_totals and calculate_column_totals:
                self.calculate_totals = True  # There's a column that requires totals to be calculated

            # Calculate how many columns can be merged for totals and group titles
            current_available_space_is_previous_column = self.maximum_available_title_colspan == column_index - 1
            if not calculate_column_totals and current_available_space_is_previous_column:
                # Can only span "Total" title on columns that we are not calculating totals on
                self.maximum_available_title_colspan += 1

            # Get data from each record for the column
            record_data = [record.get(column_id, {}) for record in data]

            # Set up currency if it does not exist
            if not currency_id and is_number:
                for record in record_data:
                    if record.get('currency_id'):
                        currency_id = record.get('currency_id')
                        column['currency_id'] = currency_id
                        break

            # Get actual record value for each record
            column_record_values = [record.get('value', '') for record in record_data]

            # Set column width
            column_width = self._get_column_size_based_on_text(column_record_values)
            column['column_width'] = column_width  # Save column width for later
            self.data_sheet.set_column(column_index, column_index, column_width)

            # Determine format
            cell_format = self._get_desired_cell_format(
                column=column_index, is_header=True, is_number=is_number, is_totals=False
            )

            # Adjust column name - include currency
            currency = currency_id and self.env['res.currency'].sudo().browse(currency_id).exists()
            if currency:
                column_name = '{0}, {1}'.format(column_name, currency.name)

            # Write column title
            self.data_sheet.write_string(self.row_pos, column_index, column_name, cell_format)

            # Compute required row height
            multiplier = self.report_options['row_height_multiplier']
            current_row_preferred_height = math.ceil(len(column_name) / float(column_width)) * multiplier
            required_row_height = max(required_row_height, current_row_preferred_height)

        self.data_sheet.set_row(self.row_pos, required_row_height)  # Adjust header row height

        self.row_pos += 1

    def write_filter_info(self):
        """
        Writes filter info on the second sheet
        """
        filter_fields = self.filters.keys()
        date_fields = ['date_from', 'date_to']  # Date fields always go first
        other_filters = [x for x in filter_fields if x not in date_fields]
        other_filters.sort()
        filter_fields = date_fields + other_filters

        column = -1

        required_header_row_height = self.report_options['minimum_row_height']

        for filter_field in filter_fields:
            row = 0
            column += 1

            field_data = self.filters.get(filter_field)
            if not field_data:
                continue

            # Set filter column name
            field_string = field_data.get('string', _('Undefined'))
            cell_format = self._get_desired_cell_format(column=column, is_header=True, sheet=2)
            self.filter_sheet.write_string(row, column, field_string, cell_format)
            row += 1

            column_values = []  # Used later to determine required column width

            # Output filter values based on type
            current_filter_value = field_data.get('current_value')
            field_type = field_data.get('type')
            cell_format = self._get_desired_cell_format(column=column, sheet=2)
            if field_type == 'date':
                cell_value = current_filter_value or '-'
                self.filter_sheet.write_string(row, column, cell_value, cell_format)
                column_values.append(cell_value)
            else:
                if not current_filter_value:
                    cell_value = _('Any')
                    self.filter_sheet.write_string(row, column, cell_value, cell_format)
                    column_values.append(cell_value)
                else:
                    if isinstance(current_filter_value, list):
                        available_values = field_data.get('list_of_values')
                        selected_values = [x for x in available_values if x[0] in current_filter_value]
                        for selected_value in selected_values:
                            cell_value = selected_value[1]
                            self.filter_sheet.write_string(row, column, cell_value, cell_format)
                            column_values.append(cell_value)
                            row += 1
                    else:
                        try:
                            cell_value = current_filter_value
                            self.filter_sheet.write_string(row, column, cell_value, cell_format)
                            column_values.append(cell_value)
                        except:
                            cell_value = _('-')
                            self.filter_sheet.write_string(row, column, cell_value, cell_format)
                            column_values.append(cell_value)

            # Set column width
            column_width = self._get_column_size_based_on_text(column_values)
            self.filter_sheet.set_column(column, column, column_width)

            # Compute required height for the row
            multiplier = self.report_options['row_height_multiplier']
            current_row_preferred_height = math.ceil(len(field_string) / float(column_width)) * multiplier
            required_header_row_height = max(required_header_row_height, current_row_preferred_height)

        self.filter_sheet.set_row(0, required_header_row_height)  # Adjust header row height

    def write_data(self, data):
        """
        Writes main data to report
        @param data: (list) list containing dictionaries of report data
        """
        number_of_columns = len(self.columns)
        self.column_totals = [0.0] * number_of_columns

        self.write_group_data(data)  # Recursively writes data to sheet for each group

        if self.calculate_totals:  # Add totals line at the bottom of the document
            # Format all cells in row
            cell_format = self._get_desired_cell_format(column=1, is_totals=True)
            for column_index in range(0, number_of_columns - 1):
                self.data_sheet.write_string(self.row_pos, column_index, '', cell_format)

            cell_format = self._get_desired_cell_format(column=0, is_totals=True)  # For the "Total" label
            needs_two_lines = self.maximum_available_title_colspan < 1  # Does the "Total" label need two lines?
            column_to_merge_to = number_of_columns-1 if needs_two_lines else self.maximum_available_title_colspan

            self.data_sheet.merge_range(self.row_pos, 0, self.row_pos, column_to_merge_to, _('Total'), cell_format)
            if needs_two_lines:
                # Write the actual totals values in another line
                self.row_pos += 1
                cell_format = self._get_desired_cell_format(column=1, is_totals=True)
                for column_index in range(0, number_of_columns - 1):
                    self.data_sheet.write_string(self.row_pos, column_index, '', cell_format)

            # Write totals values
            for column_index, column in enumerate(self.columns):
                if not column.get('calculate_totals'):
                    # Write empty string so that the cell has the same style
                    self.data_sheet.write_string(self.row_pos, column_index, '', cell_format)
                    continue

                # Get cell format and adjust it based on currency
                currency_id = column.get('is_number') and column.get('currency_id')
                cell_format = self._get_desired_cell_format(column=column_index, is_totals=True)
                self.adjust_number_format(cell_format, currency_id)

                # Some applications like libreoffice do not recalculate formulas thus we have to manually compute it
                column_total = self.column_totals[column_index]
                # Join sum() formulas from the child groups to form one large formula
                sum_formula = '=' + '+'.join(
                    group_total_formulas[column_index] for group_total_formulas in self.group_totals_formulas
                ) if self.group_totals_formulas else '0.0'
                sum_formula = self.fix_cell_formula(sum_formula)

                # Write column total to cell
                self.data_sheet.write_formula(self.row_pos, column_index, sum_formula, cell_format, column_total)

            self.row_pos += 1

    def write_group_data(self, data):
        # Adjust group info
        self.outline_level += 1
        self.number_of_groups += 1

        number_of_columns = len(self.columns)

        # Build a list of zero values as sum formulas for current outline level
        if len(self.group_totals_formulas) <= self.outline_level:
            self.group_totals_formulas.append(['0.0'] * number_of_columns)

        # Get group data
        group_data = data.get('children', list())
        child_groups = data.get('subgroups', list())
        group_name = data.get('name')

        # Create a copy of current column totals to calculate the difference later
        column_totals_before_group_data = list(self.column_totals)

        group_info_row = self.row_pos
        if group_name:
            # Write group name based on the available columns to merge
            cell_format = self._get_desired_cell_format(column=0, is_totals=True, is_number=False)
            minimum_row_height = DEFAULT_REPORT_OPTIONS.get('minimum_row_height')
            self.data_sheet.set_row(self.row_pos, minimum_row_height, None, {'level': self.outline_level})
            needs_two_lines = self.maximum_available_title_colspan < 1  # Does the group name need two lines?
            column_to_merge_to = number_of_columns - 1 if needs_two_lines else self.maximum_available_title_colspan
            self.data_sheet.merge_range(self.row_pos, 0, self.row_pos, column_to_merge_to, group_name, cell_format)
            cell_format = self._get_desired_cell_format(
                column=min(1, len(self.columns)),  # column = 1 just so it's not the first column (no borders)
                is_totals=True, is_number=False
            )
            if needs_two_lines:
                self.row_pos += 1
                self.data_sheet.set_row(self.row_pos, minimum_row_height, None, {'level': self.outline_level})
                column_to_set_styles_from = 0
            else:
                # Write group header style to cells after the cell that's been merged
                column_to_set_styles_from = column_to_merge_to

            # Write style that columns where totals are not calculated have the same style
            for column_index in range(column_to_set_styles_from, number_of_columns):
                self.data_sheet.write_string(self.row_pos, column_index, '', cell_format)

            group_info_row = self.row_pos  # To know which row to write the totals in
            self.row_pos += 1

        sum_formula_row_from = self.row_pos + 1
        self.outline_level += 1
        # Loop through data
        for record_line in group_data:
            required_row_height = self.report_options['minimum_row_height']

            # Loop through each column
            for i in range(0, len(self.columns)):

                # Get column data
                column = self.columns[i]
                column_id = column.get('identifier')
                if not column_id:
                    continue

                # Get record values
                record_column_values = record_line.get(column_id, {})
                cell_value = record_column_values.get('display_value') or record_column_values.get('value')

                is_number = column.get('is_number', False) and isinstance(cell_value, (float, int, long))
                calculate_total = column.get('calculate_totals')
                cell_format = self._get_desired_cell_format(column=i, is_number=is_number)  # Get cell format
                if is_number:
                    currency_id = record_column_values.get('currency_id') or column.get('currency_id')
                    if calculate_total:
                        self.column_totals[i] = self.column_totals[i] + cell_value

                    self.adjust_number_format(cell_format, currency_id)

                    self.data_sheet.write_number(self.row_pos, i, cell_value, cell_format)
                else:
                    cell_value = cell_value or ''
                    self.data_sheet.write_string(self.row_pos, i, cell_value, cell_format)

                multiplier = self.report_options['row_height_multiplier']
                column_width = column.get('column_width', 0.0)
                current_row_preferred_height = math.ceil(len(str(cell_value)) / float(column_width)) * multiplier
                required_row_height = max(required_row_height, current_row_preferred_height)

            # Adjust row height and set group level
            self.data_sheet.set_row(self.row_pos, required_row_height, None, {'level': self.outline_level})
            self.row_pos += 1
        sum_formula_row_to = max(self.row_pos, sum_formula_row_from)

        self.outline_level -= 1
        for child_group_index, child_group in enumerate(child_groups):
            # Recursively call same method for child groups
            self.write_group_data(child_group)
            # Combine child group formulas with current level group formulas
            for column_index in range(0, len(self.columns)):
                child_column_formula = self.group_totals_formulas[self.outline_level+1][column_index]
                self.group_totals_formulas[self.outline_level][column_index] += '+' + child_column_formula
            self.group_totals_formulas[self.outline_level+1] = ['0.0'] * number_of_columns  # Reset child group formulas

        for column_index, column in enumerate(self.columns):
            if not column.get('calculate_totals'):
                continue

            # Format group formula
            column_letter = xl_col_to_name(column_index)
            if group_data and sum_formula_row_from <= sum_formula_row_to:
                sum_formula = 'SUM({0}{1}:{0}{2})'.format(column_letter, sum_formula_row_from, sum_formula_row_to)
            else:
                sum_formula = '0.0'  # Group has no data, only child groups

            # Get sum formulas from child groups
            child_group_formulas = list(self.group_totals_formulas[self.outline_level:])
            child_group_formulas = '+'.join(
                child_group_formula[column_index] for child_group_formula in child_group_formulas
            )

            total_cell_formula = '=' + sum_formula
            if child_group_formulas:
                total_cell_formula += '+' + child_group_formulas

            total_cell_formula = self.fix_cell_formula(total_cell_formula)
            self.group_totals_formulas[self.outline_level][column_index] = total_cell_formula.replace('=', '')

            if not group_name:
                continue  # No group name therefore nothing to write to report

            cell_format = self._get_desired_cell_format(column=column_index, is_totals=True, is_number=True)

            # Calculate the totals based on what the totals were before and what they are after writing child group data
            previous_column_total = column_totals_before_group_data[column_index]
            current_column_total = self.column_totals[column_index]
            group_column_total = current_column_total - previous_column_total

            self.data_sheet.write_formula(
                group_info_row, column_index, total_cell_formula, cell_format, group_column_total
            )

        self.outline_level -= 1

    def get_raw_data(self, data):
        """ Joins grouped data together and returns a single list with all the data """
        child_groups = data.get('subgroups', list())
        raw_data = data.get('children', list())
        for child_group in child_groups:
            raw_data += self.get_raw_data(child_group)
        return raw_data

    def configure_sheet_properties(self):
        """ Configures sheets for dynamic report """
        self.data_sheet.freeze_panes(1, 0)  # Freeze header row
        self.data_sheet.set_zoom(90)  # Set the zoom when the document is opened

        # Fit sheets to a single page with the report being as long as necessary
        self.data_sheet.fit_to_pages(1, 0)
        self.filter_sheet.fit_to_pages(1, 0)

        # Set paper to A4
        self.data_sheet.set_paper(9)
        self.filter_sheet.set_paper(9)

        # Set landscape if required
        if self.report_options.get('orientation', 'landscape') == 'landscape':
            self.data_sheet.set_landscape()
            self.filter_sheet.set_landscape()

        # Don't allow modifying filter sheet. No password is set so lock can be disabled
        self.filter_sheet.protect()

    def configure_sheet_footers(self):
        report_footer = '&C&10{}&R&P/&N'.format(_('Created using RoboLabs'))

        # Set header that's seen when printing the report
        company_name = self.env.user.company_id.name
        header = '&L&15{}&C&20{}'.format(company_name, self.report_name)
        self.data_sheet.set_header(header)
        # Set footer that's seen when printing the report
        self.data_sheet.set_footer(report_footer)

        # Set header that's seen when printing the filter sheet
        company_name = self.env.user.company_id.name
        filter_title = '{} {}'.format(self.report_name, _('filters'))
        header = '&L&15{}&C&20{}'.format(company_name, filter_title)
        self.filter_sheet.set_header(header)
        # Set footer that's seen when printing the filter sheet
        self.filter_sheet.set_footer(report_footer)

    def generate_xlsx_report(self, workbook, data, record):
        """ Generates the dynamic report with the data provided """
        self.reset_init_values()
        self._define_formats(workbook)  # Define the essential workbook formats

        # Get necessary data
        self.report_name = data.get('report_name', '')
        self.filters = data.get('filters', list())
        self.columns = data.get('columns', list())
        report_data = data.get('report_data', {})

        raw_data = self.get_raw_data(report_data)  # Ungroup data to correctly determine column formatting

        self._set_report_options(data.get('report_options', {}))  # Sets specific report options.

        # Create two sheets
        self.data_sheet = workbook.add_worksheet(self.report_name)
        self.filter_sheet = workbook.add_worksheet(_('Filters'))

        # Set up columns and write the report data
        self.set_up_columns(raw_data)
        self.write_data(report_data)

        self.write_filter_info()  # Write filter info in the second sheet so it's known which filters have been used

        self.configure_sheet_properties()
        self.configure_sheet_footers()


DynamicXLSXReport('report.account_dynamic_reports.dynamic_xlsx_report', 'res.company')
