# -*- coding: utf-8 -*-

import ast
import json

from odoo import _, api, fields, models
from odoo.addons.account_dynamic_reports.models.dynamic_report_data_processor import DynamicReportDataProcessor
from odoo.addons.account_dynamic_reports.tools.date_tools import get_date_range_selection_from_selection


class DynamicReport(models.AbstractModel):
    _name = 'dynamic.report'
    _inherit = ['dynamic.report.dom', 'dynamic.report.filters', 'dynamic.report.options', 'dynamic.report.grouping',
                'dynamic.report.sorting', 'dynamic.report.pdf.export.settings', 'dynamic.report.xlsx.export']

    _dr_base_name = ''  # Use this variable to set the report name
    _report_tag = None  # Override in each report which tag to use

    @api.multi
    def name_get(self):
        res = list()
        for rec in self:
            report_name = _(rec._dr_base_name)
            if rec.date_from:
                report_name += ' {} {}'.format(_('from'), rec.date_from)
            if rec.date_to:
                report_name += ' {} {}'.format(_('to'), rec.date_to)
            res.append((rec.id, report_name))
        return res

    report_data = fields.Text(string='Report data in JSON format')
    refresh_data = fields.Boolean(string='Force refresh data with the next data reload')

    # DATA METHODS =====================================================================================================

    @api.multi
    def _get_report_data(self):
        """
        Main method that returns the data for the report
        :return: (list) a list of dictionaries containing data with column identifier equal keys
        """
        self.ensure_one()
        return []  # To be overridden for each report

    @api.multi
    def get_stored_report_data(self):
        """ Gets stored report data"""
        self.ensure_one()
        data = self.report_data
        if not data:
            return
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return
        return data

    @api.multi
    def store_report_data(self, data):
        """ Stores report data so it does not have to be looked up again when rendering the PDF or XLSX report """
        self.ensure_one()
        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            return
        try:
            encoded_data = json.dumps(data)
        except (ValueError, TypeError, MemoryError):
            encoded_data = None
        if encoded_data:
            self.report_data = encoded_data

    @api.multi
    def get_report_data(self):
        """
        Refreshes the report data and stores it. Should be executed after report filters change. Returns the new data.
        """
        self.ensure_one()
        self = self._update_self_with_report_language()
        self.check_report_access_rights()
        data = None
        if not self.refresh_data:
            data = self.get_stored_report_data()
        if not data:
            data = self.with_context(force_refresh=True)._get_report_data()
            self.store_report_data(data)
        self.write({'refresh_data': False})
        return data

    # END OF DATA METHODS ==============================================================================================

    # COLUMN METHODS ===================================================================================================

    @api.multi
    def get_shown_column_data(self):
        self.ensure_one()
        column_data = self.get_report_column_data()
        columns = [column for column in column_data if column.get('shown')]
        if not columns:
            columns = [column for column in column_data if column.get('shown_by_default')]
        return columns

    @api.multi
    def get_report_columns(self, extra_domain=None):
        self.ensure_one()
        if not extra_domain:
            extra_domain = list()
        report_model = self.env['ir.model'].sudo().search([('model', '=', self._name)])[0]
        domain = [('report_model_id', '=', report_model.id)] + extra_domain
        context = self._context.copy()
        if 'lang' not in context:
            context.update({'lang': self.determine_language_code()})
        return self.env['dynamic.report.column'].sudo().with_context(context).search(domain)

    @api.multi
    def get_report_column_data(self):
        self.ensure_one()
        column_data = self.get_report_columns().read()
        report_settings = self.get_report_settings()
        if report_settings:
            shown_column_identifiers = report_settings.get_shown_column_identifiers()
            index_map = {v: i + 1 for i, v in enumerate(shown_column_identifiers)}
            column_data.sort(key=lambda x: index_map.get(x.get('identifier'), True))
            for column in column_data:
                column['shown'] = bool(index_map.get(column.get('identifier'), False))
        return column_data

    # END OF COLUMN METHODS ============================================================================================

    # DOM METHODS ======================================================================================================

    @api.multi
    def generate_dynamic_report_dom(self, language=None):
        """
        Checks currently enabled group by fields and the stored group by fields to determine if the report should be
        reloaded, refreshes data if necessary, creates a report document object model and returns it
        @return: (DynamicReportDOMGroup) Dynamic report document object model group containing subgroups and elements
        """
        data = self.get_report_data()
        group_by = self.get_stored_group_by_identifiers()
        dynamic_report_dom = self.create_dynamic_report_dom_from_data(data, language, group_by)
        return dynamic_report_dom

    @api.multi
    def get_render_data(self, language=None):
        """
        Creates a report DOM and gets the render data
        @return: (dict) render data
        """
        # Get sorting data
        sort_by = self.get_report_sorting()

        # Get which columns to render and how
        column_render_data = self.get_report_column_data()

        if not language:
            language = self.determine_language_code()
        # Create a base data group to render
        base_data_group = self.generate_dynamic_report_dom(language=language)

        # Generate the render data
        render_data = self.env['dynamic.report.dom'].get_render_data(base_data_group, column_render_data, sort_by)
        return render_data

    @api.multi
    def format_report_data_in_html(self, groups_in_separate_tables=False):
        """
        Gets report data in html format.
        :return: (str) HTML code containing the data
        """
        self.ensure_one()
        language = self.determine_language_code()
        render_data = self.get_render_data(language=language)
        columns = self.get_shown_column_data()
        data_processor = DynamicReportDataProcessor(self.env, language, render_data, columns, groups_in_separate_tables)
        html = data_processor.render_data_html()
        return html

    # END OF DOM METHODS ===============================================================================================

    # ACTION METHODS ===================================================================================================

    @api.multi
    def action_view(self):
        self.ensure_one()
        context = self._context.copy()
        context['wizard_id'] = self.id
        report_name = _(self._dr_base_name)
        context['title'] = report_name
        if self._context.get('force_refresh_data'):
            self.write({'refresh_data': True})
        self = self._update_self_with_report_language()
        return {
            'type': 'ir.actions.client',
            'name': report_name,
            'tag': self._report_tag,
            'context': context
        }

    @api.multi
    def action_pdf(self, data=None, sort_by=None):
        """ Button function for PDF """
        self.ensure_one()
        if self._context.get('force_refresh_data') or (data and data.get('force_refresh_data')):
            self.write({'refresh_data': True})
        return self.env['dynamic.report.pdf.export'].prepare_pdf_export(self, sort_by)

    @api.multi
    def prepare_xlsx_data(self):
        report_group = self.generate_dynamic_report_dom()
        return {
            'columns': self.get_shown_column_data(),
            'report_group': report_group,
            'report_data': report_group.get_full_data(),
            'report_name': self.display_name,
            'filters': self.sudo().get_filters_from_wizard_fields()
        }

    @api.multi
    def action_xlsx(self, data=None, sort_by=None):
        """ Button function for XLSX export """
        self.ensure_one()

        if self._context.get('force_refresh_data') or (data and data.get('force_refresh_data')):
            self.write({'refresh_data': True})

        self = self._update_self_with_report_language()

        # Check if threading is enabled
        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        if not threaded:
            return self._action_xlsx()
        return self.action_background_xlsx()

    @api.multi
    def action_open_report_settings(self):
        self.ensure_one()
        if self._name != 'dynamic.report':
            action = self.env.ref('account_dynamic_reports.dynamic_report_change_report_settings_action').read()[0]
            context = ast.literal_eval(action.get('context', str()))
            context.update({'report_model': self._name})
            action['context'] = context
        else:
            action = self.env.ref('account_dynamic_reports.dynamic_report_change_global_settings_action').read()[0]
        return action

    # END OF ACTION METHODS ============================================================================================

    # OTHER METHODS ====================================================================================================

    @api.multi
    def get_report_settings(self):
        self.ensure_one()
        global_settings = self.env['dynamic.report.global.settings'].get_global_dynamic_report_settings()
        return global_settings.get_report_settings(self._name)

    @api.multi
    def determine_language_code(self):
        return self.report_language or self._context.get('lang') or 'lt_LT'

    @api.multi
    def check_report_access_rights(self):
        self.ensure_one()
        return True

    @api.model
    def get_dates_from_range(self, date_range):
        company = self.env.user.company_id
        return get_date_range_selection_from_selection(date_range, company.fiscalyear_last_day,
                                                       company.fiscalyear_last_month)

    @api.multi
    def update_group_by_selection(self, group_by):
        """
        Determines if report data should be reloaded when storing group by fields
        @param group_by:
        @return:
        """
        self.ensure_one()
        if not isinstance(group_by, list):
            return
        res = super(DynamicReport, self).update_group_by_selection(group_by)
        group_by = self.process_selected_group_by_identifiers(group_by)
        # Determine if report should be reloaded
        requires_report_to_be_reloaded = any(
            field.requires_report_to_be_reloaded for field in self.group_by_field_ids if field.identifier in group_by
        )
        if requires_report_to_be_reloaded:
            self.write({'refresh_data': True})
        return res

    @api.multi
    def store_sorting_data(self, sorting_data):
        """ Updates the sorting order based on data from JS """
        self.ensure_one()
        shown_columns = self.get_shown_column_data()
        column_to_set_sorting_by = sorting_data.get('column')
        try:
            column_to_set_sorting_by = shown_columns[column_to_set_sorting_by].get('identifier')
            direction = 'descending' if sorting_data.get('direction', 'ascending') == 'descending' else 'ascending'
            self.set_report_sorting([{'field': column_to_set_sorting_by, 'direction': direction}])
        except (KeyError, ValueError):
            return

    @api.multi
    def _update_self_with_report_language(self):
        context = self._context.copy()
        context['lang'] = self.determine_language_code()
        return self.with_context(context)

    # END OF OTHER METHODS =============================================================================================
