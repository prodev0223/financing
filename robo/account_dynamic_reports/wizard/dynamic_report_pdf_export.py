# -*- coding: utf-8 -*-

import json
import threading
from datetime import datetime

from odoo import models, api, fields, _, tools, SUPERUSER_ID, exceptions

from bs4 import BeautifulSoup

from odoo.api import Environment


class DynamicReportPDFExport(models.TransientModel):
    _name = 'dynamic.report.pdf.export'

    report_model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    report_id = fields.Integer(required=True)
    show_company_info_in_header = fields.Boolean(string="Show company info in header")
    report_purpose = fields.Selection([
        ('internal', 'For internal purposes'),
        # ('external', 'For third parties')  # TODO not rendered correctly
    ], string='Report purpose', default='internal', help='Defines which report layout should be used')
    show_header = fields.Boolean("Show report header", default=True)
    show_footer = fields.Boolean("Show report footer", default=True)
    show_filters = fields.Boolean("Show report filters")
    filter_location = fields.Selection([
        ('top', 'Top of the report'),
        ('bottom', 'Bottom of the report'),
        # ('separate_page', 'On a separate page')  # TODO
    ], default='top')
    show_groups_in_separate_tables = fields.Boolean('Show groups in separate tables')

    @api.model
    def prepare_pdf_export(self, original_report, sort_by=None):
        if not original_report:
            return

        model_name = original_report._name
        report_model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)

        export_object = self.create({
            'report_model_id': report_model.id,
            'report_id': original_report.id,
        })

        return export_object.show_export_action()

    @api.multi
    def _get_dynamic_report(self):
        self.ensure_one()
        report = self.env[self.report_model_id.model].browse(self.report_id)
        report = report._update_self_with_report_language()
        return report

    @api.multi
    def show_export_action(self):
        self.ensure_one()
        form_action = self.env.ref('account_dynamic_reports.dynamic_report_pdf_export_action').read()[0]
        form_action['res_id'] = self.id
        return form_action

    @api.multi
    def export_pdf(self):
        self.ensure_one()

        self.sudo().unlink_related_reports()  # Unlink previous reports

        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        if threaded:
            user_id = self.env.user.id
            report_name = self._get_report_display_name()
            now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

            # Create a new environment for creating a report job, create the job and close the environment so report
            # history is saved if there's any exception in the generate report method
            new_cr = self.pool.cursor()
            new_env = api.Environment(new_cr, SUPERUSER_ID, self.env.context)
            import_job_id = new_env['robo.report.job'].create({
                'report_name': report_name,
                'execution_start_date': now,
                'state': 'in_progress',
                'user_id': user_id,
                'job_type': 'export'
            }).id
            new_cr.commit()
            new_cr.close()

            # Start the thread
            report_generator = threading.Thread(target=self.prepare_threaded_pdf_report_generation,
                                                args=(self.id, import_job_id))
            report_generator.start()

            # Return the action which displays information on where to find the report
            action = self.env.ref('robo.action_open_robo_report_job').read()[0]
            action.update({
                'view_mode': 'form', 'res_id': import_job_id, 'view_id': self.env.ref('robo.form_robo_report_job').id
            })  # Force form view of the created import job
            return action

        self.generate_pdf_report()  # Generate new report
        report_identifier = self._get_report_external_id()
        return self.env['report'].with_context(landscape=True).get_action(self, report_identifier)

    @api.multi
    def unlink(self):
        res = super(DynamicReportPDFExport, self).unlink()
        self.sudo().unlink_related_reports()
        return res

    @api.multi
    def unlink_related_reports(self):
        self.ensure_one()
        all_report_identifiers = [x._get_report_external_id() for x in self]
        report_models = self.mapped('report_model_id')
        all_views = self.env['ir.ui.view'].search([('model', 'in', report_models.mapped('model'))])

        for report_model in report_models:
            export_wizards_by_report = self.filtered(lambda e: e.report_model_id == report_model)

            report_identifiers = [x._get_report_external_id() for x in export_wizards_by_report]

            report_views = all_views.filtered(lambda view: view.xml_id in report_identifiers)
            report_views.mapped('model_data_id').sudo().unlink()
            report_views.sudo().unlink()

        self.env['ir.actions.report.xml'].search([('report_name', 'in', all_report_identifiers)]).unlink()

    @api.multi
    def _get_report_view_name(self):
        self.ensure_one()
        dynamic_report = self._get_dynamic_report()
        return '{}_{}'.format(dynamic_report._name.replace('.', '_'), dynamic_report.id)

    @api.multi
    def _get_report_external_id(self):
        self.ensure_one()
        dynamic_report = self._get_dynamic_report()
        return '{}.{}'.format(dynamic_report._module, self._get_report_view_name())

    @api.multi
    def _get_report_display_name(self):
        self.ensure_one()
        dynamic_report = self._get_dynamic_report()
        display_name = dynamic_report.display_name or ''
        return display_name

    @api.multi
    def generate_report_xml(self):
        self.ensure_one()
        arch_base = '''<?xml version="1.0"?>
        <t t-name="{report_identifier}">
            <t t-call="report.html_container">
                <div class="page">
                    {report_layout}
                    {report_header}
                    {filters_top}
                    {report_data}
                    {report_footer}
                    {filters_bottom}
                </div>
            </t>
        </t>
        '''

        report = self._get_dynamic_report()

        report_layout = self.get_layout()

        report_data = report.format_report_data_in_html(groups_in_separate_tables=self.show_groups_in_separate_tables)
        report_data = self.process_html_data_for_pdf(report_data)

        report_header = report.get_pdf_header() or self.get_default_pdf_header()

        report_footer = report.get_pdf_footer()

        report_identifier = self._get_report_external_id()

        rendered_filters = self.get_applied_filters()
        filters_top = rendered_filters if self.filter_location == 'top' else ''
        filters_bottom = rendered_filters if self.filter_location == 'bottom' else ''

        report_xml = arch_base.format(
            report_identifier=report_identifier,
            report_layout=report_layout,
            report_header=report_header,
            report_data=report_data,
            report_footer=report_footer,
            filters_top=filters_top,
            filters_bottom=filters_bottom
        )

        return report_xml

    @api.multi
    def get_applied_filters(self):
        self.ensure_one()
        if not self.show_filters:
            return ''
        report = self.sudo()._get_dynamic_report()
        applied_filters = list()
        applied_booleans = list()
        filter_fields = report._get_dynamic_report_front_filter_fields()
        filter_fields.sort()

        for report_filter_field in filter_fields:
            field = report._fields.get(report_filter_field)  # Get field attributes
            field_type = field.type  # Determine field type

            field_name = report.get_report_field_name(field)
            if not field_name:
                continue
            try:
                field_value = report[report_filter_field]
            except KeyError:
                field_value = None

            if field_type in ['many2many', 'many2one']:
                if not field_value:
                    applied_filters.append({'title': field_name, 'selection': _('All')})
                    continue

                # Try to give a name to all of the selected values
                named_values = None
                for comodel_field_to_try in ['code', 'number', 'name', 'display_name']:
                    try:
                        named_values = field_value.mapped(comodel_field_to_try)
                        break
                    except KeyError:
                        pass
                if not named_values:
                    named_values = field_value if all(isinstance(x, (str, basestring)) for x in field_value) else None
                if not named_values:
                    continue

                # Format the named values
                number_of_values = len(named_values)
                displayed_value = ''
                if number_of_values > 5:
                    displayed_value = '({}) '.format(number_of_values)
                # This is the maximum number of characters the selected choices can span. If named selection exceeds
                # this value - the shown applied selection ends with the last selection exceeding this value and how
                # many others are there is shown, e.g. (if set to 5) "(11) A, B, C, D, E and 6 others"
                maximum_number_of_characters_to_show = 50

                # Get the values to actually show
                values_to_actually_show = list()
                for named_value in named_values:
                    if maximum_number_of_characters_to_show <= 0:
                        break
                    named_value_length = len(named_value)
                    values_to_actually_show.append(named_value)
                    maximum_number_of_characters_to_show -= named_value_length

                # Calculate how many other values are there that should be mentioned
                number_of_other_values_to_mention = number_of_values - len(values_to_actually_show)

                # Adjust/format the displayed value
                displayed_value += ', '.join(values_to_actually_show)
                if number_of_other_values_to_mention > 0:
                    displayed_value += ' ' + _('and {} others').format(number_of_other_values_to_mention)

                applied_filters.append({'title': field_name, 'selection': displayed_value})
            elif field_type == 'boolean':
                if not field_value:
                    continue
                applied_booleans.append(field_name)
            else:
                if field_type == 'selection':
                    try:
                        field_value = dict(field._description_selection(self.env)).get(field_value)
                    except KeyError:
                        pass
                applied_filters.append({'title': field_name, 'selection': field_value or '-'})

        if applied_booleans:
            applied_filters.append({'title': _('Other options'), 'selection': ', '.join(applied_booleans)})

        return self.env['ir.qweb'].render(
            'account_dynamic_reports.AppliedPDFFilters', {'applied_filters': applied_filters}
        )

    @api.multi
    def get_layout(self):
        self.ensure_one()
        if self.show_company_info_in_header:
            report_layout = 'internal_layout' if self.report_purpose == 'internal' else 'external_layout'
            return '''<t t-call="report.{}"/>'''.format(report_layout)
        return ''

    @api.multi
    def get_default_pdf_header(self):
        self.ensure_one()
        report = self._get_dynamic_report()
        return self.env['ir.qweb'].render('account_dynamic_reports.DefaultDynamicPDFReportHeader', {
            'company': self.env.user.company_id,
            'report_name': report.display_name,
            'date_from': report.date_from,
            'date_to': report.date_to
        })

    @api.model
    def process_html_data_for_pdf(self, html):
        soup = BeautifulSoup(html, features="lxml")

        # Remove all no_print elements
        for element_to_remove in soup.find_all(class_='no_print'):
            element_to_remove.decompose()

        for table_header in soup.find_all("", {'class': 'group_table_header'}):
            table_header_style = 'text-align: center;'
            if table_header.name == 'h2':
                table_header_style += ' font-weight: bold !important;'
            table_header['style'] = table_header.get('style', '') + table_header_style

        # Set styles
        default_border_style = "1px solid black"
        group_header_style = "font-weight: bold; font-style: italic;"

        empty_cells = soup.find_all("th", {"class": "empty-cell"}) + soup.find_all("td", {"class": "empty-cell"})
        for empty_cell in empty_cells:
            empty_cell['style'] = empty_cell.get('style', '') + "min-width: 10px;"

        for table in soup.find_all("table"):
            table_rows = table.find_all("tr")
            for table_row in table_rows:
                style = "padding: 2px; vertical-align: middle; border-collapse: collapse !important; " \
                        "break-inside: avoid;"
                bottom_border_style = "border-bottom: 1px solid lightgray;"

                next_row = table_row.find_next('tr')
                if next_row and next_row.get('class') and "group-title-border-top" in next_row['class']:
                    bottom_border_style = "border-bottom: {};".format(default_border_style)

                row_class = table_row.get('class')
                if row_class:
                    if 'group-title-border-top' in row_class:
                        bottom_border_style = ""
                        style += " border-top: {};".format(default_border_style)
                    if 'group-title-row' in row_class:
                        style += " {}".format(group_header_style)
                table_row['style'] = table_row.get('style', '') + "{} {};".format(style, bottom_border_style)
            if table_rows:
                table_rows[-1]['style'] = table_rows[-1].get('style', '') + \
                                          "border-bottom: none; border-top: {}; break-before: avoid;".format(default_border_style)

            for table_cell in table.find_all('td') + table.find_all('th'):
                table_cell['style'] = table_cell.get('style', '') + 'padding: 1px 3px;'

            thead_row = table.find("thead").find("tr")
            if thead_row:
                thead_row['style'] = thead_row.get('style', '') + \
                                     "border-bottom: {}; font-weight: bold;".format(default_border_style)

            for table_header in table.find_all("th"):
                table_header['style'] = table_header.get('style', '') + \
                                        "font-size': 12px; padding: 5px !important; vertical-align: middle;"

            for table_cell in table.find_all("td"):
                table_cell['style'] = table_cell.get('style', '') + \
                                      "font-size': 12px; padding: 5px !important; vertical-align: middle;"

        html = soup.prettify()
        return html

    @api.model
    def prepare_threaded_pdf_report_generation(self, wizard_id, import_job_id):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT', 'threaded_report': True})

            # Re-browse the object with new cursor
            import_job = env['robo.report.job'].browse(import_job_id)
            report_object = env['dynamic.report.pdf.export'].browse(wizard_id)

            try:
                report_object.generate_pdf_report()
                report_identifier = report_object._get_report_external_id()
                action = env['report'].with_context(landscape=True).get_action(self, report_identifier)
                data = import_job.render_report(action)
                base64_file = data.get('base64_file')
                exported_file_name = data.get('exported_file_name')
                exported_file_type = data.get('exported_file_type')
            except Exception as exc:
                new_cr.rollback()
                import_job.write({
                    'state': 'failed',
                    'fail_message': str(exc.args[0]),
                    'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                })
            else:
                import_job.write({
                    'state': 'succeeded',
                    'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'exported_file': base64_file,
                    'exported_file_name': exported_file_name,
                    'exported_file_type': exported_file_type
                })

            import_job.post_message()
            new_cr.commit()
            new_cr.close()

    @api.multi
    def generate_pdf_report(self):
        self.ensure_one()
        if not self.env.user.is_premium_manager():
            raise exceptions.AccessError(_("You don't have sufficient rights to perform this action"))

        report_name = self._get_report_view_name()
        report_xml = self.generate_report_xml()
        dynamic_report = self._get_dynamic_report()

        view = self.env['ir.ui.view'].sudo().create({
            'name': report_name,
            'model': dynamic_report._name,
            'type': 'qweb',
            'arch_base': report_xml
        })

        self.env['ir.model.data'].sudo().create({
            'module': dynamic_report._module,
            'name': report_name,
            'model': 'ir.ui.view',
            'res_id': view.id,
        })

        report = self.env['ir.actions.report.xml'].sudo().create({
            'name': self._get_report_display_name(),
            'report_type': 'qweb-pdf',
            'model': dynamic_report._name,
            'report_name': self._get_report_external_id(),
            'paperformat_id': self.env.ref('report.paperformat_a4_landscape_narrow').id,
        })

        return report
