# -*- coding: utf-8 -*-
from odoo.addons.account_dynamic_reports.models.dynamic_report_dom_element import DEFAULT_REPORT_ELEMENT_TEMPLATE
from odoo.addons.account_dynamic_reports.models.dynamic_report_dom_group import DEFAULT_REPORT_GROUP_TEMPLATE

NUMBER_TYPES = (int, float, long)


class DynamicReportDataProcessor(object):

    def __init__(self, env, language, render_data, column_data, groups_in_separate_tables=False):
        self.columns = column_data
        self.render_data = render_data
        self.groups = list()
        self.number_of_groups = 0
        self.has_child_elements = False
        self.env = env
        self.language = language
        self.groups_in_separate_tables = groups_in_separate_tables

    def get_data_table_template_ext_id(self):
        return 'account_dynamic_reports.DynamicReportPDFTable'

    def get_group_ids(self, group_data):
        group_ids = list()
        group_id = group_data.get('group_id')
        if group_id:
            group_ids.append(group_id)
        subgroups = group_data.get('subgroups', list())
        for subgroup in subgroups:
            group_ids += self.get_group_ids(subgroup)
        return group_ids

    def render_data_html(self):
        if not self.render_data or not self.columns:
            return

        if self.groups_in_separate_tables:
            return self.render_groups_in_separate_tables(self.render_data)
        else:
            return self.render_data_table(self.render_data)

    def render_groups_in_separate_tables(self, render_data):
        # Get subgroups and remove them from render data so they are not rendered as a single table
        subgroups = render_data.get('subgroups')
        render_data['subgroups'] = list()

        # Render base group (only the title if there's no child elements
        res = self.render_data_table(render_data, render_group_title=True)

        # Render subgroups in the same manner
        for subgroup in subgroups:
            res += self.render_groups_in_separate_tables(subgroup)
        return res

    def render_data_table(self, render_data, render_group_title=False):
        # Check if a table will have data that needs to be rendered (children and subgroups)
        has_data_to_render = render_data.get('children') or render_data.get('subgroups')

        group_title = render_data.get('group_title')
        if render_group_title:
            render_data['group_title'] = None  # Reset group title in render data since it should be rendered separately
        res = ''

        # Get basic group data in case the group title is rendered separately
        group_level = render_data.get('group_level')
        max_group_level = render_data.get('max_group_level')
        first_and_only_group = group_level == -1 and group_level == max_group_level
        group_name = render_data.get('name')

        # Only render a table if there's data to render of if the group has a name (and no elements) when the group
        # title is not rendered separately or if it's the first and only group
        if has_data_to_render or ((group_name or first_and_only_group) and not render_group_title):
            rendered_data = self.render_group_data(render_data)  # Get render data used for rendering
            table_template_ext_id = self.get_data_table_template_ext_id()  # Determine which table template to use
            # Render data as a table
            res += self.env['ir.qweb'].render(table_template_ext_id, {
                'columns': self.columns,
                'renderedGroupData': rendered_data,
                'any_child_has_child_elements': render_data['any_child_has_child_elements'],
                'max_group_level': render_data['max_group_level'],
                'group_totals': render_data['group_totals'],
            })

        # Check if group title should be rendered separately
        if not render_group_title or not group_title or not isinstance(group_level, int):
            return res

        # Render group title
        rendered_group_title = self.env['ir.qweb'].render('account_dynamic_reports.DynamicReportGroupTableHeader', {
            'group_level': group_level,
            'group_title': group_title
        })

        res = rendered_group_title + res  # Update rendered data with the group title

        return res

    def render_data_row(self, row_data):
        template = row_data.get('template', DEFAULT_REPORT_ELEMENT_TEMPLATE)
        if all(not cell.get('value') for cell in row_data.get('cells', [])):
            return ''  # Don't render row if all the cells are empty
        return self.env['ir.qweb'].render(template, row_data)

    def render_group_data(self, render_data):
        rendered_group = ''

        # Render group title
        group_template = render_data.get('template', DEFAULT_REPORT_GROUP_TEMPLATE)
        group_title = render_data.get('group_title', '')
        group_title_row = self.env['ir.qweb'].render(group_template, render_data)

        # Render subgroups
        subgroups = render_data.get('subgroups', list())
        rendered_subgroups = ''.join(self.render_group_data(subgroup) for subgroup in subgroups)
        rendered_group += rendered_subgroups

        # Render data rows
        data_rows = render_data.get('children', list())
        rendered_data_rows = ''.join(self.render_data_row(data_row) for data_row in data_rows)
        rendered_group += rendered_data_rows

        # Determine if the group title row (containing group totals) should go at the top of the data or at the bottom
        if group_title:
            rendered_group = group_title_row + rendered_group
        else:
            rendered_group += group_title_row

        return rendered_group
