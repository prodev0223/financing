# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import models, fields, api, tools, exceptions, _
from lxml import etree, objectify
from dateutil.relativedelta import relativedelta
import logging
from ... import e_vmi_tools as v_tools


_logger = logging.getLogger(__name__)
shareholders_per_page = 4
static_name = 'FR0438.ffdata'


class FR0438(models.TransientModel):
    """
    Wizard that is used to generate and export FR0438 ff-data file to VMI
    """
    _name = 'e.vmi.fr0438'

    @api.model
    def _generated_file(self):
        return self._context.get('generated_xml', str())

    @api.model
    def _date_from(self):
        return datetime.now() - relativedelta(day=1)

    @api.model
    def _date_to(self):
        return datetime.now() - relativedelta(day=31)

    @api.model
    def _shareholder_line_ids(self):
        line_ids = []
        shareholder_ids = self.env['res.company.shareholder'].search([])
        line_obj = self.env['e.vmi.fr0438.line']
        for shareholder_id in shareholder_ids:
            res = line_obj.create({
                'shareholder_id': shareholder_id.id,
                'shareholder_address': shareholder_id.shareholder_address
            })
            line_ids.append(res.id)
        return [(6, 0, line_ids)]

    shareholder_line_ids = fields.One2many('e.vmi.fr0438.line', 'wizard_id',
                                           string='Akcininkų sąrašas', default=_shareholder_line_ids)
    date_from = fields.Date(string='Mokestinio laikotarpio pradžia', default=_date_from, required=True)
    date_to = fields.Date(string='Mokestinio laikotarpio pabaiga', default=_date_to, required=True)

    # Used in different wizard form
    generated_file = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=_generated_file)
    file_name = fields.Char(string='Failo pavadinimas', default='FR0438.ffdata')

    @api.multi
    def validate_constraints(self):
        """
        Validate FR0438 form constraints
        :return: None
        """
        self.ensure_one()
        if not self.shareholder_line_ids:
            raise exceptions.Warning(_('Nėra duomenų apie akcininkus'))

        for en, line in enumerate(self.shareholder_line_ids, 1):
            if not line.shareholder_id.shareholder_personcode or len(line.shareholder_id.shareholder_personcode) > 20:
                raise exceptions.Warning(
                    _('{} Eilutės akcininko kodas nėra įrašytas arba viršija leistiną 20 simbolių dydį'.format(en)))
            if not line.shareholder_address or len(line.shareholder_address) > 64:
                raise exceptions.Warning(
                    _('{} Eilutės akcininko adresas nėra įrašytas arba viršija leistiną 64 simbolių dydį'.format(en)))
            if not line.shareholder_id.shareholder_name or len(line.shareholder_id.shareholder_name) > 32:
                raise exceptions.Warning(
                    _('{} Eilutės akcininko vardas nėra įrašytas arba viršija leistiną 32 simbolių dydį'.format(en)))

    @api.multi
    def generate_xml(self):
        self.ensure_one()
        form, root = v_tools.get_report_header('FR0438')
        pages = objectify.Element('Pages')
        form.append(pages)

        structured_page_data = list(v_tools.prepare_chunks(self.shareholder_line_ids, shareholders_per_page))
        page = self.get_first_static_page(page_numbers=len(structured_page_data))
        pages.append(page)

        for en, page_data in enumerate(structured_page_data):
            page = objectify.Element('Page')

            while len(page_data) != shareholders_per_page:
                page_data.append(self.env['e.vmi.fr0438.line'])

            for num in range(1, shareholders_per_page + 1):
                self.shareholder_fields_set(page_num=en, num_in_page=num, obj=page_data[num - 1], page_obj=page)
            pages.append(page)

        objectify.deannotate(root)
        etree.cleanup_namespaces(root)
        generated_xml = etree.tostring(root, xml_declaration=True, encoding='utf-8')
        return generated_xml

    @api.multi
    def generate_report(self):
        self.ensure_one()
        self.validate_constraints()
        generated_xml = self.generate_xml()
        final_data = generated_xml.encode('utf8').encode('base64')
        company_data = self.sudo().env.user.company_id.get_report_company_data()

        if self._context.get('upload_vmi'):
            try:
                self.env.user.upload_eds_file(
                    final_data, static_name, self.date_from,
                    registry_num=company_data['code']
                )
            except Exception as exc:
                _logger.info(exc.args[0])
                self.sudo().env.user.upload_eds_file(
                    final_data, static_name, self.date_from,
                    registry_num=company_data['code']
                )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0438',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_FR0438_download').id,
            'context': {'generated_xml': final_data},
        }

    @api.model
    def get_first_static_page(self, page_numbers=1):
        """
        Page is not going to be used in ROBO, however we must include it in ff-data file
        :param page_numbers: Extra pages, 4 shareholders per page
        :return: first-page (str)
        """
        company_id = self.sudo().env.user.company_id
        company_data = company_id.get_report_company_data()

        res = '''<Page PageDefName="FR0438" PageNumber="1" xmlns="">
            <Fields Count="33">
              <Field Name="B_MM_ID">{}</Field>
              <Field Name="B_MM_Pavad">{}</Field>
              <Field Name="B_UzpildData">{}</Field>
              <Field Name="B_ML_DataNuo">{}</Field>
              <Field Name="B_ML_DataIki">{}</Field>
              <Field Name="E5"></Field>
              <Field Name="E6"></Field>
              <Field Name="E7"></Field>
              <Field Name="E8"></Field>
              <Field Name="E9"></Field>
              <Field Name="E10"></Field>
              <Field Name="B_Tiesioginis">0</Field>
              <Field Name="B_Netiesioginis">0</Field>
              <Field Name="B_KartuSuSusijusiaisAsmenimis">0</Field>
              <Field Name="E12"></Field>
              <Field Name="E13"></Field>
              <Field Name="E14"></Field>
              <Field Name="E15"></Field>
              <Field Name="E16"></Field>
              <Field Name="E17"></Field>
              <Field Name="E18"></Field>
              <Field Name="E19"></Field>
              <Field Name="E20"></Field>
              <Field Name="E21"></Field>
              <Field Name="E22"></Field>
              <Field Name="E23"></Field>
              <Field Name="E24"></Field>
              <Field Name="E25"></Field>
              <Field Name="E26"></Field>
              <Field Name="E27">0</Field>
              <Field Name="E29">{}</Field>
              <Field Name="B_FormNr" />
              <Field Name="B_FormVerNr" />
            </Fields>
          </Page>'''.format(
            company_data['code'],
            company_data['name'],
            datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            self.date_from,
            self.date_to,
            page_numbers
        )
        return objectify.fromstring(res)

    @api.multi
    def shareholder_fields_set(self, page_num, num_in_page, obj, page_obj):
        """
        Sets shareholder field nodes on passed xml page object
        :param page_num: number of exact page
        :param num_in_page: number of shareholder in the page (4 per page)
        :param obj: shareholder line from the wizard
        :param page_obj: etree xml page object
        :return: None
        """
        self.ensure_one()
        if not obj:
            data = [str()] * 7
        else:
            shareholder_type = self.shareholder_type_mapper(obj)
            company_name = str()
            person_name = str()
            if shareholder_type in ['JA']:
                company_name = obj.shareholder_id.shareholder_name
            else:
                person_name = obj.shareholder_id.shareholder_name
            data = [shareholder_type, str(), obj.shareholder_id.shareholder_personcode,
                    obj.share_percentage, company_name, person_name, obj.shareholder_address]
        for en, data_line in enumerate(data):
            v_tools.set_node_and_tag(
                p_node=page_obj,
                c_text=data_line,
                c_tag='PB{}{}-{}'.format(page_num, en, num_in_page))

    @api.multi
    def shareholder_type_mapper(self, obj):
        """
        Maps and returns specific string if shareholder is a person and a company
        :param obj: shareholder line obj
        :return: shareholder type string for the form
        """
        self.ensure_one()
        return 'FA' if obj.shareholder_id.shareholder_type \
            or obj.shareholder_id.shareholder_type in ['person'] else 'JU'

    @api.model
    def action_create_wizard(self):
        """
        Action to create self record before opening the wizard, so the on-changes behave correctly
        :return: wizard action
        """
        res = self.env['e.vmi.fr0438'].create({})
        return {
            'name': _('VMI FR0438'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('e_ataskaitos.vmi_FR0438').id,
            'res_id': res.id,
            'res_model': 'e.vmi.fr0438',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


FR0438()
