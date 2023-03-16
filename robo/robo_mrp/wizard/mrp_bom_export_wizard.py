# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class MrpBomExportWizard(models.TransientModel):
    _name = 'mrp.bom.export.wizard'
    _description = '''
    Wizard allows user to export BOM as PDF
    or XLS files based on the mode
    '''

    bom_id = fields.Many2one('mrp.bom', string='Komplektacija')
    bom_explosion_mode = fields.Selection(
        [('explode_none', 'Neskaidyti komponentų'),
         ('explode_all', 'Skaidyti komponentus')],
        string='Komplektacijos išskaidymo tipas',
        default='explode_none',
    )
    recursive_bom_production = fields.Boolean(
        compute='_compute_recursive_bom_production'
    )

    @api.multi
    def _compute_recursive_bom_production(self):
        """Check whether recursive production is activated in the system. Used in form view"""
        recursive_bom_production = self.sudo().env.user.company_id.enable_recursive_bom_production
        for rec in self:
            rec.recursive_bom_production = recursive_bom_production

    @api.multi
    def button_export_pdf(self):
        """Method trigger from the button that calls export_data with PDF flag"""
        self.ensure_one()
        return self.export_data(export_type='pdf')

    @api.multi
    def button_export_xls(self):
        """Method trigger from the button that calls export_data with XLS flag"""
        self.ensure_one()
        return self.export_data(export_type='xls')

    @api.multi
    def export_data(self, export_type):
        """
        Method that exports current BOM
        either into PDF or XLS file.
        If company has exploded bom production
        activated, user can select either exploded
        or only parent component mode
        """
        self.ensure_one()
        # Render the components based on the explosion mode
        bom = self.bom_id
        if self.recursive_bom_production and self.bom_explosion_mode == 'explode_all':
            components_html = bom.bom_line_ids.compose_exploded_bom_lines_table()
            report_mode_name = _('Išskaidyta komplektacija')
        else:
            components_html = bom.bom_line_ids.render_bom_lines()
            report_mode_name = _('Komplektacija')

        # Render the components table
        components_html_table = self.env['ir.qweb'].render(
            'robo_mrp.bom_line_table_print_template', {'table_body': components_html}
        )
        # Suggested by Odoo community, but still a sketchy way of checking.
        # Even if HTML field is empty in the form, in python it contains <p><br></p>.
        comments_exist = False if not bom.comments or bom.comments == '<p><br></p>' else True

        # Format print date
        dn = datetime.now()
        print_date = _('{}m. {}mėn. {}d.').format(dn.year, str(dn.month).zfill(2), str(dn.day).zfill(2))

        # Prepare the data
        data = {
            'report_mode_name': report_mode_name,
            'product_name': bom.product_tmpl_id.display_name,
            'quantity_display': '{} {}'.format(bom.product_qty, bom.product_uom_id.name),
            'code': bom.code,
            'comments': bom.comments,
            'comments_exist': comments_exist,
            'component_table': components_html_table,
            'print_date': print_date,
            'expiry_dates_enabled': False,
        }
        # Check if BOM expiry date functionality is enabled
        expiry_dates = self.sudo().env.user.company_id.enable_bom_expiry_dates
        if expiry_dates:
            data.update({
                'date_from': bom.valid_from,
                'date_to': bom.valid_to or _('Neapibrėžta'),
                'expiry_dates_enabled': True,
            })

        report_obj = self.env['report'].sudo()
        xls_export = export_type == 'xls'
        # If export type is XLS, add extra params
        if xls_export:
            # Compose detailed header
            header = ' / Produktas {}'.format(bom.product_tmpl_id.display_name)
            if expiry_dates:
                header += ' / Galiojimo periodas {} - {}'.format(bom.valid_from, bom.valid_to)
            # Add context to report _object
            report_obj = report_obj.with_context(
                xls_report=True, date_header=header
            )
        # Return report action
        action = report_obj.get_action(
            self.bom_id, 'robo_mrp.mrp_bom_report', data=data
        )
        exported_file_name = '{} - {}.{}'.format(report_mode_name, bom.product_tmpl_id.display_name, export_type)
        return self.env['robo.report.job'].sudo().render_report_with_attachment(
            action=action, calling_record=self, forced_xls=xls_export,
            forced_file_name=exported_file_name
        )

