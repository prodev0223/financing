# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions
from lxml import etree, objectify
from odoo.tools.translate import _
from ... import e_vmi_tools as vt
import logging


_logger = logging.getLogger(__name__)

STATIC_REPORT_NAME = 'FR0521'


class FR0521(models.TransientModel):
    """
    Wizard that is used to generate and export FR0521 ff-data file to VMI
    """
    _name = 'e.vmi.fr0521'

    @api.model
    def _default_generated_file(self):
        """Get generated FR0521 file from the context"""
        return self._context.get('generated_xml', str())

    @api.model
    def _default_date_from(self):
        """Default date_from -- First day of previous year"""
        return datetime.utcnow() - relativedelta(years=1, month=1, day=1)

    @api.model
    def _default_date_to(self):
        """Default date_to -- Last day of previous year"""
        return datetime.utcnow() - relativedelta(years=1, month=12, day=31)

    @api.model
    def _default_fuel_line_ids(self):
        """
        Generate FR0521 fuel lines based on the period
        used as a 'default' field method and triggered on the onchange
        :return: [(6, 0, [IDs of 'e.vmi.fr0521.line'])]
        """
        date_from = self.date_from or self._default_date_from().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = self.date_to or self._default_date_to().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        invoice_lines = self.env['account.invoice.line'].search([
            ('product_id.name', 'in', vt.PRODUCT_NAMES_0521),
            ('invoice_id.state', 'in', ['open', 'paid']),
            ('invoice_id.date_invoice', '>=', date_from),
            ('invoice_id.date_invoice', '<=', date_to),
        ])

        fuel_lines = []
        for fuel_type in vt.PRODUCT_NAMES_0521:
            filtered_invoice_lines = invoice_lines.filtered(lambda x: x.product_id.name == fuel_type)
            total_quantity = sum(filtered_invoice_lines.mapped('quantity'))
            if not tools.float_is_zero(total_quantity, precision_digits=2):
                converted_quantity = tools.float_round(
                    total_quantity * vt.PRODUCT_RATES_0521[fuel_type], precision_digits=3)

                fuel_line = self.env['e.vmi.fr0521.line'].create({
                    'name': fuel_type,
                    'type': vt.PRODUCT_CODES_0521[fuel_type],
                    'quantity': converted_quantity,
                })
                fuel_lines.append(fuel_line.id)

        return [(6, 0, fuel_lines)]

    date_from = fields.Date(string='Deklaracijos periodo pradžia', default=_default_date_from, required=True)
    date_to = fields.Date(string='Deklaracijos periodo pabaiga', default=_default_date_to, required=True)

    # Relational fields
    fuel_line_ids = fields.One2many(
        'e.vmi.fr0521.line', 'wizard_id', string='Kuro pardavimų sąrašas', default=_default_fuel_line_ids)

    # Used in different wizard form
    generated_file = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=_default_generated_file)
    file_name = fields.Char(string='Failo pavadinimas', default='FR0521.ffdata')

    # On-changes // ---------------------------------------------------------------------------------------------------

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        """
        Re-generate fuel_line_ids if date_from or date_to is changed
        and dates are of year period, otherwise return warning message
        """
        if self.date_from and self.date_to:
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            # Make comparisons using date_to
            year_start_dt = date_to_dt - relativedelta(day=1, month=1)
            year_end_dt = date_to_dt + relativedelta(day=31, month=12)

            if year_end_dt != date_to_dt or year_start_dt != date_from_dt:
                return {'warning': {'title': _('Įspėjimas'), 'message': _('Periodas privalo būti vieneri metai!')}}
        self.fuel_line_ids = self._default_fuel_line_ids()

    # Methods Called From Buttons -------------------------------------------------------------------------------------

    @api.multi
    def button_generate_report(self):
        """
        Generate FR0521 XML file and open the download window
        :return: report download wizard action (dict)
        """
        self.ensure_one()
        final_data = self.generate_xml()
        return self.action_download_form(final_data)

    @api.multi
    def button_generate_send_report(self):
        """
         Generate FR0521 XML file, send it to VMI
         and open the download window
        :return: report download wizard action (dict)
        """
        self.ensure_one()
        final_data = self.generate_xml()
        company_data = self.env.user.company_id.get_report_company_data()
        try:
            self.env.user.upload_eds_file(
                final_data, '{}.ffdata'.format(STATIC_REPORT_NAME),
                self.date_from, registry_num=company_data['code']
            )
        except Exception as exc:
            _logger.info(exc.args[0])
            self.sudo().env.user.upload_eds_file(
                final_data, '{}.ffdata'.format(STATIC_REPORT_NAME),
                self.date_from, registry_num=company_data['code']
            )
        return self.action_download_form(final_data)

    # Main Methods // -------------------------------------------------------------------------------------------------

    @api.multi
    def generate_xml(self):
        """
        Validate necessary constraints and proceed to
        generate FR0521 report XML file based on specified requirements
        :return: base64 encoded XML file (str)
        """
        self.ensure_one()
        self.validate_constraints()
        form, root = vt.get_report_header(STATIC_REPORT_NAME)
        pages = objectify.Element('Pages')
        form.append(pages)

        region = self.env.user.company_id.savivaldybe
        structured_pages_data = list(vt.prepare_chunks(
            self.fuel_line_ids, vt.PAGE_POPULATION_THRESHOLD_0521))
        for p_en, page_data in enumerate(structured_pages_data, 1):
            # Objectify Page
            page = objectify.Element('Page')

            # Set element attributes
            page.attrib['PageDefName'] = STATIC_REPORT_NAME
            page.attrib['PageNumber'] = str(p_en)
            page.attrib['xmlns'] = str()

            # Populate data to per-page threshold
            while len(page_data) != vt.PAGE_POPULATION_THRESHOLD_0521:
                page_data.append(self.env['e.vmi.fr0521.line'])

            page_header = self.get_page_header()
            # Write field values
            for en, line in enumerate(page_data, 1):
                self.fields_set(num_in_page=en, obj=line, page_obj=page_header, region=region)

            # Append two empty static elements
            vt.set_node_and_tag(p_node=page_header, c_text=str(), c_tag='E22')
            vt.set_node_and_tag(p_node=page_header, c_text=str(), c_tag='E23')

            # Append elements
            page.append(page_header)
            pages.append(page)

        # Cleanup
        objectify.deannotate(root)
        etree.cleanup_namespaces(root)
        generated_xml = etree.tostring(root, xml_declaration=True, encoding='utf-8')
        final_data = generated_xml.encode('utf8').encode('base64')
        return final_data

    @api.multi
    def validate_constraints(self):
        """
        Validate FR0521 form constraints
        :return: None
        """
        self.ensure_one()
        # More constraints to come in the future
        if not self.fuel_line_ids:
            raise exceptions.Warning(_('Šiame periode nerasta kuro duomenų!'))

    # Utility Methods ------------------------------------------------------------------------------------------------

    @api.model
    def get_page_header(self):
        """
        Populate and convert first bunch of fields
        that hold company info to etree object
        :return: etree instance (object)
        """
        company_id = self.env.user.company_id
        company_data = company_id.get_report_company_data()
        date_now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        company_block = '''
        <Fields Count="{}">
              <Field Name="B_FormNr"/>
              <Field Name="B_FormVerNr"/>
              <Field Name="B_MM_Pavad">{}</Field>
              <Field Name="B_MM_ID">{}</Field>
              <Field Name="B_MM_Tel">{}</Field>
              <Field Name="B_MM_Faksas"/>
              <Field Name="B_MM_Adresas">{}</Field>
              <Field Name="B_MM_Epastas">{}</Field>
              <Field Name="E7"/>
              <Field Name="B_UzpildData">{}</Field>
              <Field Name="B_ML_Metai">{}</Field>
              <Field Name="B_ML_Pusmetis" />
              <Field Name="B_ML_Ketvirtis" />
              <Field Name="E20">1,000</Field>
        </Fields>
        '''.format(vt.STATIC_FIELD_COUNT_0521,
                   company_data['name'], company_data['code'],
                   company_data['phone'], company_data['full_address'],
                   company_data['email'], date_now, self.date_from[:4])
        return objectify.fromstring(company_block)

    @api.multi
    def fields_set(self, num_in_page, obj, page_obj, region):
        """
        Sets fuel field nodes on passed xml page object
        :param num_in_page: number of fuel entries in the page (8 per page)
        :param obj: shareholder line from the wizard
        :param page_obj: etree xml page object
        :param region: Static region code
        :return: None
        """
        self.ensure_one()
        count_start = 11
        if not obj:
            data = [str()] * 10
        else:
            # Used static values (magic numbers) are not meant to change
            # Consulted the accountants
            data = ['A', obj.type, region, str(), 1, 0.0, 1.00, obj.quantity, str(), str()]
        for en, data_line in enumerate(data, count_start):
            if en == len(data) + count_start:
                en += 1  # Field numbering goes like this on second to last: 19 -> 21
            vt.set_node_and_tag(
                p_node=page_obj,
                c_text=data_line,
                c_tag='E{}-{}'.format(en, num_in_page))

    # CRUD Methods // -------------------------------------------------------------------------------------------------

    @api.multi
    def write(self, vals):
        """
        Write method override
        ! IMPORTANT - Bug in api, it provides values with (1, id, vals), so doesn't link to them
        # (See bug #21285, #14761) This overload is needed because there is api.onchange method
        :param vals: values to write
        :return: write result (bool)
        """
        if 'fuel_line_ids' in vals:
            actions = vals['fuel_line_ids']
            new_actions = [(5,)]
            if isinstance(actions, list):
                for action in actions:
                    if len(action) == 3 and action[0] == 1:
                        new_actions.append((4, action[1]))
            vals['fuel_line_ids'] = new_actions
        return super(FR0521, self).write(vals)

    # Actions // ------------------------------------------------------------------------------------------------------

    @api.model
    def action_create_wizard(self):
        """
        Action to create self record before opening the wizard,
        so the on-changes behave correctly
        :return: wizard action (dict)
        """
        res = self.env['e.vmi.fr0521'].create({})
        return {
            'name': 'VMI FR0521',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('e_ataskaitos.form_e_vmi_fr0521').id,
            'res_id': res.id,
            'res_model': 'e.vmi.fr0521',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def action_download_form(self, final_data):
        """
        Return action that opens FR0521 download wizard
        :param final_data: generated FR0521 XML file (str)
        :return: download wizard action (dict)
        """
        return {
            'name': 'VMI FR0521',
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0521',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.form_e_vmi_fr0521_download').id,
            'context': {'generated_xml': final_data},
        }


FR0521()
