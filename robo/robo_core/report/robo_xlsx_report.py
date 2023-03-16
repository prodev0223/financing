# -*- coding: utf-8 -*-

import math

from xlsxwriter.utility import xl_col_to_name

try:
    from odoo.addons.report_xlsx.report.report_xlsx import ReportXlsx
    from xlsxwriter.utility import xl_rowcol_to_cell
except ImportError:
    ReportXlsx = object

from odoo import _

DEFAULT_REPORT_OPTIONS = {
    'maximum_column_width': 55,  # Maximum size for any single column
    'minimum_column_width': 15,  # Minimum size for any single column
    'char_width_ratio': 1.0,  # Number of characters will be multiplied by this value to get the size of each column
    'orientation': 'landscape',  # Report orientation (portrait/landscape)
    'minimum_row_height': 17,  # Minimum row height
    'row_height_multiplier': 14,  # Used to calculate necessary row height. Increase to have more padding for rows.
    'border_color': '#000000',
}


class RoboXLSXReport(ReportXlsx):

    def _set_report_options(self, custom_options=None):
        """
        Set default report options
        @param custom_options: dictionary with data that overrides default report options
        """
        report_options = DEFAULT_REPORT_OPTIONS
        if custom_options:
            report_options.update(custom_options)
        self.report_options = report_options

    def _define_formats(self, workbook):
        """ Add cell formats to current workbook."""

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

    def _get_desired_cell_format(self, sheet, column=1, is_header=False, is_number=False, is_totals=False):
        """
        Gets the cell format based on the cell and its properties
        @param sheet: Which sheet is it.
        @param column: Column to get format for (default is 1 to get for regular/middle cell with no borders)
        @param is_header: Is the data header data
        @param is_number: Is the cell data a number
        @param is_totals: Is the cell data a totals row
        @return: Workbook format that should be used
        """
        first_column = column == 0
        last_column = column == len(sheet.columns) - 1

        if is_header:
            if first_column:
                if is_number:
                    return self.format_header_number_column_border_left
                return self.format_header_border_left
            elif last_column:
                if is_number:
                    return self.format_header_number_column_border_right
                return self.format_header_border_right
            if is_number:
                return self.format_header_number_column
            return self.format_header
        elif is_totals:
            if first_column:
                if is_number:
                    return self.line_total_format_border_left
                return self.line_total_left_format_border_left
            elif last_column:
                if is_number:
                    return self.line_total_format_border_right
                return self.line_total_left_format_border_right
            if is_number:
                return self.line_total_format
            return self.line_total_left_format
        else:
            if first_column:
                if is_number:
                    return self.regular_number_format_border_left
                return self.regular_data_format_border_left
            elif last_column:
                if is_number:
                    return self.regular_number_format_border_right
                return self.regular_data_format_border_right
            if is_number:
                return self.regular_number_format
            return self.regular_data_format

    def _get_number_format(self, currency_id=None):
        """
        Gets number format (based on the currency if provided)
        @param currency_id: (int) res.currency id
        @return: (string) number format
        """
        currency = currency_id and self.env['res.currency'].browse(currency_id).exists()
        if not currency:
            return '#,##0.00'
        return currency.excel_format

    def adjust_number_format(self, fmt, currency_id):
        number_format = self._get_number_format(currency_id)
        fmt.set_num_format(number_format)

    def _get_column_size_based_on_text(self, text):
        """
        Computes the column size based on values of that column
        @param text: (str) value that is going to be in the column
        @return: (float) column size
        """
        minimum_column_width = self.report_options['minimum_column_width']
        maximum_column_width = self.report_options['maximum_column_width']
        char_width_ratio = self.report_options['char_width_ratio']

        required_size = max(minimum_column_width, len(text)) * char_width_ratio
        available_size = min(required_size, maximum_column_width)

        return available_size

    def set_up_columns(self, columns, sheet):
        """
        Sets up the columns for the report. Sets the column width as well as the titles for each column.
        @param columns: (list) columns of the data
        @param sheet: (object) sheet object to set the column on
        """

        required_row_height = self.report_options['minimum_row_height']

        for i in range(0, len(columns)):
            column = columns[i]

            # Get column data
            column_id = column.get('name')
            column_name = column.get('string', '')
            currency_id = column.get('currency_id')
            is_number = column.get('is_number')
            if not column_id:
                continue

            column_width = self._get_column_size_based_on_text(column_name)  # Set column width
            column['column_width'] = column_width  # Save column width for later
            sheet.set_column(i, i, column_width)

            # Determine format
            cell_format = self._get_desired_cell_format(sheet=sheet, column=i, is_header=True, is_number=is_number,
                                                        is_totals=False)

            # Adjust column name - include currency
            currency = currency_id and self.env['res.currency'].sudo().browse(currency_id).exists()
            if currency_id:
                column_name = '{0}, {1}'.format(column_name, currency.name)

            # Write column title
            sheet.write_string(0, i, column_name, cell_format)

            # Compute required row height
            multiplier = self.report_options['row_height_multiplier']
            current_row_preferred_height = math.ceil(len(column_name) / float(column_width)) * multiplier
            required_row_height = max(required_row_height, current_row_preferred_height)

        sheet.set_row(0, required_row_height)  # Adjust header row height

    def write_sheet_data(self, sheet, data):
        """
        Writes provided data as lines to report
        @param sheet: (object) sheet to write to
        @param data: (list) list containing dictionaries of report data
        """

        # Set up current row (next one after the header)
        row_pos = 1

        # Variables to calculate column totals
        columns = sheet.columns
        column_totals = [0.0] * len(columns)
        show_totals_row = False
        calculate_total_row_from = row_pos

        # Loop through data
        for record_line in data:

            required_row_height = self.report_options['minimum_row_height']

            # Loop through each column
            for i in range(0, len(columns)):

                # Get column data
                column = columns[i]
                column_id = column.get('name')
                if not column_id:
                    continue

                # Get record values
                record_column_values = record_line.get(column_id, {})
                cell_value = record_column_values.get('value', '')

                # Update column width
                required_column_width = self._get_column_size_based_on_text(str(cell_value))
                current_column_width = column['column_width']
                if required_column_width > current_column_width:
                    sheet.set_column(i, i, required_column_width)
                    column['column_width'] = required_column_width  # Save column width

                is_number = column.get('is_number', False) or isinstance(cell_value, (float, int, long))
                is_actual_number = isinstance(cell_value, (float, int, long))
                calculate_total = column.get('calculate_total')
                # Get cell format
                cell_format = self._get_desired_cell_format(sheet=sheet, column=i, is_number=is_number)
                if is_actual_number:
                    currency_id = record_column_values.get('currency_id') or column.get('currency_id')
                    if calculate_total:
                        if not show_totals_row:
                            show_totals_row = True
                        column_totals[i] = column_totals[i] + cell_value

                    self.adjust_number_format(cell_format, currency_id)
                    sheet.write_number(row_pos, i, cell_value, cell_format)
                else:
                    sheet.write_string(row_pos, i, cell_value, cell_format)

                multiplier = self.report_options['row_height_multiplier']
                column_width = column.get('column_width', 0.0)
                current_row_preferred_height = math.ceil(len(str(cell_value)) / float(column_width)) * multiplier
                required_row_height = max(required_row_height, current_row_preferred_height)

            sheet.set_row(row_pos, required_row_height)  # Adjust row height
            row_pos += 1

        if show_totals_row:
            maximum_available_totals_title_col_span = -1  # Used to display "Total" on totals line
            for i in range(0, len(columns)):
                column = columns[i]
                calculate_total = column.get('calculate_total')
                if not calculate_total and maximum_available_totals_title_col_span == i - 1:
                    # Can only span "Total" title on columns that we are not calculating totals on
                    maximum_available_totals_title_col_span = i
                    continue

                # Some applications like libreoffice do not recalculate formulas thus we have to manually compute it
                column_total = column_totals[i]
                column_letter = xl_col_to_name(i)
                sum_formula = '=SUM({0}{1}:{0}{2})'.format(column_letter, calculate_total_row_from, row_pos)

                # Update column width
                required_column_width = self._get_column_size_based_on_text(str(column_total))
                current_column_width = column['column_width']
                if required_column_width > current_column_width:
                    sheet.set_column(i, i, required_column_width)
                    column['column_width'] = required_column_width  # Save column width

                currency_id = column.get('is_number') and column.get('currency_id')
                cell_format = self._get_desired_cell_format(sheet=sheet, column=i, is_totals=True)
                self.adjust_number_format(cell_format, currency_id)
                sheet.write_formula(row_pos, i, sum_formula, cell_format, column_total)

            if maximum_available_totals_title_col_span >= 0:
                # Write "Total" title
                col_to = maximum_available_totals_title_col_span
                cell_format = self._get_desired_cell_format(sheet=sheet, column=0, is_totals=True)
                sheet.merge_range(row_pos, 0, row_pos, col_to, _('Total'), cell_format)

            row_pos += 1

    def _set_up_sheet(self, report_name, workbook, sheet_data):
        """
        Sets up sheets based on their data
        @param report_name: (str) Report name (to be shown on header)
        @param workbook: (object) Workbook to add the sheets to
        @param sheet_data: (dict) Sheet data to set options from
        """
        new_sheet = workbook.add_worksheet(sheet_data.get('name'))  # Create a new sheet

        # Get and set up columns for the newly created sheet
        columns = sheet_data.get('columns')
        if columns:
            new_sheet.columns = columns
            self.set_up_columns(columns, new_sheet)
            new_sheet.column_count = len(columns)

        # Freeze the top row
        freeze_panes = sheet_data.get('freeze_panes', (1, 0))
        if freeze_panes:
            new_sheet.freeze_panes(freeze_panes[0], freeze_panes[1])

        # Set sheet zoom
        new_sheet.set_zoom(sheet_data.get('zoom', 90))

        # Fit sheet to a single page with the report being as long as necessary
        new_sheet.fit_to_pages(1, 0)

        # Set sheet paper to specified one or A4
        new_sheet.set_paper(sheet_data.get('paper', 9))

        # Set footer that's seen when printing the report
        report_footer = sheet_data.get('footer') or '&C&10{}&R&P/&N'.format(_('RoboLabs'))
        new_sheet.set_footer(report_footer)

        # Set header that's seen when printing the report
        company_name = self.env.user.company_id.name
        header = sheet_data.get('header') or '&L&15{}&C&20{}'.format(company_name, report_name)
        new_sheet.set_header(header)

        # Set landscape if required (default always true)
        if sheet_data.get('landscape', True):
            new_sheet.set_landscape()

        return new_sheet

    def generate_xlsx_report(self, workbook, data, record):
        self._set_report_options()
        self._define_formats(workbook)  # Define Robo XLSX report formats

        sheets = data.get('sheets', list())  # Get all sheets
        report_name = data.get('report_name') or record._description  # Get report name
        for sheet in sheets:
            # Set up each sheet according to its data
            new_sheet = self._set_up_sheet(report_name, workbook, sheet)
            self.write_sheet_data(new_sheet, sheet.get('data', list()))
