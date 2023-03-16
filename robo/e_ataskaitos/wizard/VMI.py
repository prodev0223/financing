# -*- coding: utf-8 -*-
import calendar
import logging
import os
from datetime import datetime
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

from dateutil.relativedelta import relativedelta
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError

from odoo import models, fields, api, tools, exceptions
from odoo.tools import float_compare, float_round
from odoo.tools.translate import _
from ..e_vmi_tools import xml_validator

_logger = logging.getLogger(__name__)

# todo: might need update
PVM_kodas = 'PVM19'
CONTACTS_MAX_LENGTH = 30


class FR0600(models.TransientModel):
    _name = 'e.vmi.fr0600'

    def _company_id(self):
        return self.env.user.company_id.id

    def _pradzia(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'FR0600.ffdata'

    company_id = fields.Many2one('res.company', string='Kompanija', default=_company_id, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    patikslinta = fields.Boolean(string='Ar patikslinta ataskaita?', default=False)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)

    @api.multi
    def get_deductible_vat_rate(self):
        return 100

    @api.multi
    def post_process_data(self, data):
        """
            Method to add some special post processing in other modules
        :param data: dict of data used in to format report
        :return: None
        """
        pass

    @api.multi
    def fr0600(self):

        self._cr.execute(
            '''
            SELECT
              code,
              tax,
              (CASE WHEN inv_type IN ('in_invoice', 'in_refund') THEN 'purchase' WHEN inv_type IN ('out_invoice', 'out_refund') THEN 'sale' ELSE 'other' end)inv_type
            FROM (
              (SELECT account_account_tag.code, sum(account_move_line.balance) as tax, account_invoice.type as inv_type
                                      FROM account_move_line
                                      LEFT JOIN account_move ON account_move_line.move_id = account_move.id AND account_move_line.date >= %s AND account_move_line.date <= %s
                                      LEFT JOIN account_tax ON account_tax.id = account_move_line.tax_line_id
                                      LEFT JOIN account_tax_account_tag ON account_tax.id = account_tax_account_tag.account_tax_id
                                      LEFT JOIN account_account_tag ON account_account_tag.id = account_tax_account_tag.account_account_tag_id
                                      LEFT JOIN account_invoice ON account_move_line.invoice_id = account_invoice.id
                                      WHERE account_move_line.tax_line_id is not NULL AND account_move.state = 'posted' AND (account_account_tag.base is null OR account_account_tag.base = FALSE)
                                      AND account_move.id = account_move_line.move_id
                                      AND (account_invoice.skip_isaf = true AND account_move_line.account_id = account_tax.account_id
                                           OR account_invoice.skip_isaf = false
                                           OR account_invoice.skip_isaf IS NULL)
                                      GROUP BY account_account_tag.code, account_account_tag.base, account_tax.id, inv_type) UNION ALL
            (SELECT account_account_tag.code, sum(account_move_line.balance) as tax, account_invoice.type as inv_type
                                      FROM account_move_line
                                      LEFT JOIN account_move ON account_move_line.move_id = account_move.id AND account_move_line.date >= %s AND account_move_line.date <= %s
                                      LEFT JOIN account_move_line_account_tax_rel ON account_move_line_account_tax_rel.account_move_line_id = account_move_line.id
                                      LEFT JOIN account_tax ON account_move_line_account_tax_rel.account_tax_id = account_tax.id
                                      LEFT JOIN account_tax_account_tag ON account_tax.id = account_tax_account_tag.account_tax_id
                                      LEFT JOIN account_account_tag ON account_account_tag.id = account_tax_account_tag.account_account_tag_id
                                      LEFT JOIN account_invoice ON account_move_line.invoice_id = account_invoice.id
                                      WHERE account_move.state = 'posted' AND (account_account_tag.base = TRUE)
                                      AND account_move.id = account_move_line.move_id
                                      GROUP BY account_account_tag.code, account_account_tag.base, account_tax.id, inv_type)) AS foo;''',
            (self.data_nuo, self.data_iki, self.data_nuo, self.data_iki)
        )
        duomenys = self._cr.fetchall()
        vat_obj = self.sudo().env['res.company.vat.status']
        vat_lines = vat_obj.search([])
        if vat_lines:
            date_froms = vat_lines.mapped('date_from')
            date_tos = vat_lines.mapped('date_to')
            date_froms.sort()
            date_tos.sort()
            first_date = date_froms[0]
            last_date = date_tos[-1]
            if self.data_nuo <= first_date <= self.data_iki:
                date_from = first_date
            else:
                date_from = self.data_nuo
            if last_date and self.data_nuo <= last_date <= self.data_iki:
                date_to = last_date
            else:
                date_to = self.data_iki
        else:
            date_from = self.data_nuo
            date_to = self.data_iki
        tax = {}
        for duom in duomenys:
            if duom[0] not in tax.keys():
                tax[duom[0]] = duom[1]
            else:
                tax[duom[0]] += duom[1]
        tax_purchase = {}
        tax_sale = {}
        for duom in duomenys:
            sale = True if duom[2] == 'sale' else False
            purchase = True if duom[2] == 'purchase' else False
            if sale:
                if duom[0] not in tax_sale.keys():
                    tax_sale[duom[0]] = duom[1]
                else:
                    tax_sale[duom[0]] += duom[1]
            if purchase:
                if duom[0] not in tax_purchase.keys():
                    tax_purchase[duom[0]] = duom[1]
                else:
                    tax_purchase[duom[0]] += duom[1]

        for k in tax_purchase.keys():
            tax_purchase[k] = int(float_round(tax_purchase[k], precision_digits=0))
        for k in tax_sale.keys():
            tax_sale[k] = -tax_sale[k]
            tax_sale[k] = int(float_round(tax_sale[k], precision_digits=0))
        for k in tax.keys():
            tax[k] = int(float_round(tax[k], precision_digits=0))

        company_data = self.company_id.get_report_company_data()
        address = str()
        street = company_data['street']
        if len(street) <= CONTACTS_MAX_LENGTH:
            address = street
            city = company_data['city']
            full_address = '{}, {}'.format(address, city)
            if city and len(full_address) <= CONTACTS_MAX_LENGTH:
                address = full_address

        company_email = self.company_id.email or ''
        company_email = company_email if len(company_email) <= CONTACTS_MAX_LENGTH else ''

        vat_account = self.env['account.account'].search(
            [('code', '=', '44923'), ('company_id', '=', self.company_id.id)], limit=1)
        if vat_account:
            relevant_move_lines = self.env['account.move.line'].search([('date', '>=', self.data_nuo),
                                                                        ('date', '<=', self.data_iki),
                                                                        ('account_id', '=', vat_account.id),
                                                                        ('move_id.state', '=', 'posted'),
                                                                        ])
            amount_27 = sum(relevant_move_lines.mapped(lambda r: r.credit - r.debit))
        else:
            amount_27 = 0.0
        amount_27 = int(float_round(amount_27, precision_digits=0))
        restore_amount = self.get_vat_restore_amount()

        if not self.company_id.evrk:
            raise exceptions.UserError(_('Nenurodytas kompanijos EVRK kodas'))
        DATA = {
            'pavad': company_data['name'] and company_data['name'][:30],  # FORM ONLY ACCEPTS 30 CHARS
            'imones_kodas': company_data['code'],
            'vat': company_data['vat_code'] and company_data['vat_code'][2:],
            'adresas': address,
            'epastas': company_email,
            'data': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'datanuo': date_from,
            'dataiki': date_to,
            'evrk': (self.company_id.evrk.code or '')[-6:] if self.company_id.evrk else '',
            'pvm_apmokestinami_sandoriai': tax_sale.get('11', 0),
            'pvm_apmokestinami_sandoriai96': tax_sale.get('12', 0),
            'pvm_neapmokestinami_sandoriai': tax_sale.get('13', 0),
            'privat_poreikiams': tax_sale.get('14', 0),
            'ilg_turt_pasigam': tax_sale.get('15', 0),
            'su_marza': tax_sale.get('16', 0),
            'prekiu_eksportas_0': tax_sale.get('17', 0),
            'es_pvm_0': tax_sale.get('18', 0),
            'kiti_pvm_0': tax_sale.get('19', 0),
            'uz_lt_ribu': tax_sale.get('20', 0),
            'is_es_prekes': tax_purchase.get('21', 0),
            'es_trikampe': tax_purchase.get('22', 0),
            'uzsienio_paslaugos': tax_purchase.get('23', 0),
            'is_ju_ES_PVM': tax_purchase.get('24', 0),
            'prekiu_paslaugu_pvm': tax_purchase.get('25', 0),
            'sumoketo_importo': tax['26'] if '26' in tax.keys() else '',
            'importo_pvm_vmi': amount_27,
            'kalendoriniu_proporcinis_pvm': self.get_deductible_vat_rate(),  # FIXME: get from settings
            'standartinio_tarifo_pvm': tax_sale.get('29', 0),
            '9proc_pvm': tax_sale.get('30', 0),
            '5proc_pvm': tax_sale.get('31', 0),
            'pvm_95': tax.get('32', 0),
            'pvm_96': tax_sale.get('33', 0) + tax_purchase.get('33', 0),
            'is_es_pard_pvm': tax.get('34', 0),
            'atskaitomas_pvm': tax.get('35', 0) + amount_27 - restore_amount,
            'pirmine_ar_patikslinta': 1 if self.patikslinta == 0 else 2,
        }

        DATA['moketinas_pvm'] = DATA['importo_pvm_vmi'] + DATA['standartinio_tarifo_pvm'] + \
                                DATA['9proc_pvm'] + DATA['5proc_pvm'] + DATA['pvm_95'] + DATA['pvm_96'] + \
                                DATA['is_es_pard_pvm'] - DATA['atskaitomas_pvm']

        self.post_process_data(DATA)

        XML = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByApp="Robo" CreatedByLogin="ROBO" CreatedOn="%(data)s">
<Form FormDefId="{DFDCC8EC-FFAB-4AA2-92E3-E20980272B19}" >
<DocumentPages>
<Group Name="Visa forma">
<ListPages>
<ListPage>FR0600</ListPage>
</ListPages>
</Group>
</DocumentPages>
<Pages Count="1">
<Page PageDefName="FR0600" PageNumber="1">
<Fields Count="40">
<Field Name="B_MM_Pavad">%(pavad)s</Field>
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="LT"></Field>
<Field Name="B_MM_PVM">%(vat)s</Field>
<Field Name="B_MM_Adresas">%(adresas)s</Field>
<Field Name="B_MM_Epastas">%(epastas)s</Field>
<Field Name="B_UzpildData">%(data)s</Field>
<Field Name="B_ML_DataNuo">%(datanuo)s</Field>
<Field Name="B_ML_DataIki">%(dataiki)s</Field>
<Field Name="E10">%(evrk)s</Field>
<Field Name="E11">%(pvm_apmokestinami_sandoriai)s</Field>
<Field Name="E12">%(pvm_apmokestinami_sandoriai96)s</Field>
<Field Name="E13">%(pvm_neapmokestinami_sandoriai)s</Field>
<Field Name="E14">%(privat_poreikiams)s</Field>
<Field Name="E15">%(ilg_turt_pasigam)s</Field>
<Field Name="E16">%(su_marza)s</Field>
<Field Name="E17">%(prekiu_eksportas_0)s</Field>
<Field Name="E18">%(es_pvm_0)s</Field>
<Field Name="E19">%(kiti_pvm_0)s</Field>
<Field Name="E20">%(uz_lt_ribu)s</Field>
<Field Name="E21">%(is_es_prekes)s</Field>
<Field Name="E22">%(es_trikampe)s</Field>
<Field Name="E23">%(uzsienio_paslaugos)s</Field>
<Field Name="E24">%(is_ju_ES_PVM)s</Field>
<Field Name="E25">%(prekiu_paslaugu_pvm)s</Field>
<Field Name="E26">%(sumoketo_importo)s</Field>
<Field Name="E27">%(importo_pvm_vmi)s</Field>
<Field Name="E28">%(kalendoriniu_proporcinis_pvm)s</Field>
<Field Name="E29">%(standartinio_tarifo_pvm)s</Field>
<Field Name="E30">%(9proc_pvm)s</Field>
<Field Name="E31">%(5proc_pvm)s</Field>
<Field Name="E32">%(pvm_95)s</Field>
<Field Name="E33">%(pvm_96)s</Field>
<Field Name="E34">%(is_es_pard_pvm)s</Field>
<Field Name="E35">%(atskaitomas_pvm)s</Field>
<Field Name="E36">%(moketinas_pvm)s</Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
<Field Name="E8">%(pirmine_ar_patikslinta)s</Field>
<Field Name="E9">1</Field>
</Fields>
</Page>
</Pages>
</Form>
</FFData>
''' % DATA

        if self._context.get('eds'):
            self.env.user.upload_eds_file(
                XML.encode('utf8').encode('base64'),
                'FR0600.ffdata', self.data_nuo,
                registry_num=company_data['code']
            )

        # -------------------------------
        attach_vals = {'res_model': 'res.company',
                       'name': 'FR0600' + '.ffdata',
                       'datas_fname': 'FR0600' + '.ffdata',
                       'res_id': self.company_id.id,
                       'type': 'binary',
                       'datas': XML.encode('utf8').encode('base64')}
        self.env['ir.attachment'].sudo().create(attach_vals)
        # --------------------------------------

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0600',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_fr0600_download').id,
            'context': {'failas': XML.encode('utf8').encode('base64')},
        }

    @api.multi
    def get_vat_restore_amount(self):
        """
        Method to be overridden
        :return: 0
        """
        return 0


FR0600()


class FR0564(models.TransientModel):
    _name = 'e.vmi.fr0564'

    @api.multi
    def auto_load(self):
        if 'file' in self._context.keys():
            return self._context['file']
        else:
            return ''

    def _file_name(self):
        return 'FR0564.ffdata'

    def default_year(self):
        return (datetime.utcnow() - relativedelta(months=1)).year

    def default_month(self):
        return (datetime.utcnow() - relativedelta(months=1)).month

    company_id = fields.Many2one('res.company', string='Kompanija', default=lambda self: self.env.user.company_id,
                                 required=True)
    fill_date = fields.Date(string='Data', default=fields.Date.today, required=True)
    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Year', default=default_year,
                            required=True)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Mėnuo', required=True,
                             default=default_month)
    file = fields.Binary(string='Ataskaita', readonly=True, default=auto_load)
    file_name = fields.Char(string='Failo pavadinimas', default=_file_name)
    ignore_missing_vat = fields.Boolean(string='Ignoruoti trūkstamų PVM kodų įspėjimus')

    @api.multi
    def FR0564(self):
        invoices = self.get_invoice_data()  # invoices.filtered(lambda r: r.country_id.intrastat)
        if not invoices:
            raise exceptions.UserError(_('Pasirinktam laikotarpiui nerasta tinkamų sąskaitų faktūrų.'))

        XML = '''<?xml version="1.0" encoding="UTF-8"?>
                <FFData Version="1" CreatedByApp="Robo" CreatedByLogin="%(created_by)s" CreatedOn="%(created_on)s">
                <Form FormDefId="{69D689D5-B191-4B58-A03C-ED0A85F76C3E}">
                '''

        company_data = self.company_id.get_report_company_data()
        company_vat = company_data['vat_code'] and company_data['vat_code'][2:]
        page_lines = []
        for idx, invoice in enumerate(invoices):
            if idx <= 8:
                if len(page_lines) < 1:
                    page_lines.append({})
                    page_lines[0]['lines'] = ''
                    page_lines[0]['total_amount'] = 0
                    page_lines[0]['field_count'] = 14  # initial 14 fields
                page_lines[0]['total_amount'] += invoice['product']
                page_lines[0]['field_count'] += 6
                page_lines[0]['lines'] += '''<Field Name="E10-%(nr)s">%(nr)d</Field>
                    <Field Name="E11-%(nr)d">%(country_code)s</Field>
                    <Field Name="E12-%(nr)d">%(partner_vat)s</Field>
                    <Field Name="E13-%(nr)d">%(product_amount)0.f</Field>
                    <Field Name="E14-%(nr)d">%(three_way_amount)0.f</Field>
                    <Field Name="E18-%(nr)d">%(service_amount)0.f</Field>''' % {
                    'nr': idx + 1,
                    'country': invoice['country_code'],
                    'country_code': invoice['country_code'],
                    'partner_vat': invoice['vat'] and len(invoice['vat']) > 2 and invoice['vat'][2:] or '',
                    'product_amount': invoice['product'] if invoice['product'] else False,
                    'service_amount': invoice['service'] if invoice['service'] else False,
                    'three_way_amount': invoice['three_way'] if invoice['three_way'] else False
                }
            else:
                page_number = (idx + 7) // 16 + 1
                row_number = ((idx - 9) - 16 * (page_number - 2)) + 1
                if len(page_lines) < page_number:
                    page_lines.append({})
                    page_lines[page_number - 1]['lines'] = ''
                    page_lines[page_number - 1]['total_amount'] = 0
                    page_lines[page_number - 1]['field_count'] = 10  # initial 10 fields
                page_lines[page_number - 1]['field_count'] += 6
                page_lines[page_number - 1]['total_amount'] += invoice['product']
                page_lines[page_number - 1]['lines'] += '''<Field Name="E10-%(row_num)s">%(nr)d</Field>
                                    <Field Name="E11-%(row_num)s">%(country_code)s</Field>
                                    <Field Name="E12-%(row_num)s">%(partner_vat)s</Field>
                                    <Field Name="E13-%(row_num)s">%(product_amount)0.f</Field>
                                    <Field Name="E14-%(row_num)s">%(three_way_amount)0.f</Field>
                                    <Field Name="E18-%(row_num)s">%(service_amount)0.f</Field>''' % {
                    'nr': idx + 1,
                    'row_num': row_number,
                    'country': invoice['country_code'],
                    'country_code': invoice['country_code'],
                    'partner_vat': invoice['vat'] and invoice['vat'][2:] or '',
                    'product_amount': invoice['product'] if invoice['product'] else 0,
                    'service_amount': invoice['service'] if invoice['service'] else 0,
                    'three_way_amount': invoice['three_way'] if invoice['three_way'] else 0,
                }
        # fill-in empty lines
        for page_index, page in enumerate(page_lines):
            if page['field_count'] < 68 and page_index == 0:
                field_count = page['field_count']
                diff = 68 - field_count
                page['field_count'] = 68
                missing_rows = diff / 6
                start_row = 9 - missing_rows + 1
                end_row = 9
                while start_row <= end_row:
                    page['lines'] += '''<Field Name="E10-%(row_num)s"></Field>
                                    <Field Name="E11-%(row_num)s"></Field>
                                    <Field Name="E12-%(row_num)s"></Field>
                                    <Field Name="E13-%(row_num)s"></Field>
                                    <Field Name="E14-%(row_num)s"></Field>
                                    <Field Name="E18-%(row_num)s"></Field>''' % {
                        'row_num': start_row
                    }
                    start_row += 1
            elif page['field_count'] < 106 and page_index > 0:
                field_count = page['field_count']
                diff = 106 - field_count
                page['field_count'] = 106
                missing_rows = diff / 6
                start_row = 16 - missing_rows + 1
                end_row = 16
                while start_row <= end_row:
                    page['lines'] += '''<Field Name="E10-%(row_num)s"></Field>
                                                    <Field Name="E11-%(row_num)s"></Field>
                                                    <Field Name="E12-%(row_num)s"></Field>
                                                    <Field Name="E13-%(row_num)s"></Field>
                                                    <Field Name="E14-%(row_num)s"></Field>
                                                    <Field Name="E18-%(row_num)s"></Field>''' % {
                        'row_num': start_row
                    }
                    start_row += 1

        total_amount = sum(page['total_amount'] for page in page_lines)

        XML += '''<DocumentPages>
                    <Group Name="Visa forma">
                        <ListPages>
                            <ListPage>FR0564</ListPage>
                        </ListPages>'''
        for idx, page in enumerate(page_lines):
            if idx == 0:
                continue
            XML += '''
                        <Group Name="Priedas_%(page_name)s" >
                            <ListPages>
                                <ListPage>%(page_name)s</ListPage>
                            </ListPages>
                        </Group>
                        ''' % {'page_name': 'FR0564P'}
        XML += '''</Group>'''

        XML += '''
        </DocumentPages>
        <Pages Count="%(page_count)s">'''

        XML += '''
                <Page PageDefName="FR0564" PageNumber="1">
                    <Fields Count="%(field_count_1)s">
                        <Field Name="B_MM_Pavad">%(company_name)s</Field>
                        <Field Name="B_MM_ID">%(company_code)s</Field>
                        <Field Name="B_MM_PVM">%(company_vat)s</Field>
                        <Field Name="B_MM_Tel">%(company_contact)s</Field>
                        <Field Name="B_UzpildData">%(fill_date)s</Field>
                        <Field Name="B_ML_Metai">%(report_year)s</Field>
                        <Field Name="B_ML_Ketvirtis"></Field>
                        <Field Name="B_ML_Menuo">%(report_month)s</Field>''' + page_lines[0][
            'lines']

        XML += '''<Field Name="E15">%(total_page_amount)0.f</Field>
                <Field Name="E16">%(total_amount)0.f</Field>
                <Field Name="E17">%(additional_page_count)d</Field>
                <Field Name="B_FormNr"></Field>
                <Field Name="B_FormVerNr"></Field>
                <Field Name="Text-20"></Field>
            </Fields>
        </Page>''' % {
            'total_page_amount': page_lines[0]['total_amount'],
            'total_amount': total_amount,
            'additional_page_count': len(page_lines) - 1
        }

        XML_Add_Pages = ''
        for idx, page in enumerate(page_lines):
            if idx == 0:
                continue
            page_number = idx + 1
            XML_Add_Pages += '''
            <Page PageDefName="%(page_name)s" PageNumber="%(page_number)d">
                <Fields Count="%(field_count)d">
                ''' % {
                'page_name': 'FR0564P',
                'page_number': page_number,
                'field_count': page['field_count']
            }
            XML_Add_Pages += page['lines']

            XML_Add_Pages += '''
                    <Field Name="E15">%(total_page_amount)0.f</Field>
                    <Field Name="LapoNr">%(sheet_number)d</Field>
                    <Field Name="B_FormNr"></Field>
                    <Field Name="B_FormVerNr"></Field>
                    <Field Name="B_MM_ID">%(company_code)s</Field>
                    <Field Name="Text-LT"></Field>
                    <Field Name="B_MM_PVM">%(company_vat)s</Field>
                    <Field Name="B_ML_Ketvirtis"></Field>
                    <Field Name="B_ML_Menuo">%(report_month)s</Field>
                    <Field Name="B_ML_Metai">%(report_year)s</Field>
                </Fields>
            </Page>''' % {
                'total_page_amount': page['total_amount'],
                'sheet_number': idx,
                'company_code': company_data['code'],
                'company_vat': company_vat,
                'report_year': self.year,
                'report_month': self.month
            }

        XML += XML_Add_Pages + '''
        </Pages>'''

        XML += '''
            </Form>
        </FFData>'''

        contact = company_data['phone'] or company_data['email'] or company_data['fax']
        XML = XML % {
            'created_by': self.env.user.name,
            'created_on': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'page_count': len(page_lines),
            'field_count_1': page_lines[0]['field_count'],
            'company_name': company_data['name'] and company_data['name'][:52],  # FORM ONLY ACCEPTS 52 CHARS
            'company_code': company_data['code'],
            'company_vat': company_vat,
            'company_contact': contact,
            'fill_date': self.fill_date,
            'report_year': self.year,
            'report_month': self.month,
        }
        if self._context.get('eds'):
            date = datetime(self.year, self.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.env.user.upload_eds_file(
                XML.encode('utf8').encode('base64'),
                'FR0564.ffdata', date,
                registry_num=company_data['code']
            )

        # -------------------------------
        attach_vals = {'res_model': 'res.company',
                       'name': 'FR0564' + '.ffdata',
                       'datas_fname': 'FR0564' + '.ffdata',
                       'res_id': self.company_id.id,
                       'type': 'binary',
                       'datas': XML.encode('utf8').encode('base64')}
        self.env['ir.attachment'].sudo().create(attach_vals)
        # --------------------------------------
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0564',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_fr0564_download').id,
            'context': {'file': XML.encode('utf8').encode('base64')},
        }

    def get_invoice_data(self):
        month_days = calendar.monthrange(self.year, self.month)[1]
        date_from = datetime(year=self.year, month=self.month, day=1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime(year=self.year, month=self.month, day=month_days).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        three_way_trading_tax = self.env['account.tax'].search([('code', '=', PVM_kodas)])
        tax_ids = three_way_trading_tax.mapped('id')
        if not tax_ids:
            tax_ids = [-1]
        pvm_exclude_codes = ['PVM1', 'PVM12', 'PVM14', 'Ne PVM']
        # pvm_exclude_ids = self.env['account.tax'].search(['|', ('code', '=', 'PVM1'), ('code', '=', 'PVM12')]).mapped(
        #     'id')
        self._cr.execute(
            '''
            select part.id as partner_id,
             case when line_tax.tax_id is null then (case when templ.acc_product_type is NULL then 'service' else templ.acc_product_type end) else 'three_way' end as trade_type,
              country.code, part.vat, SUM(inv_line.price_subtotal_signed) as total_amount
                from account_invoice inv
                inner join res_country country on country.id = inv.intrastat_country_id
                inner join account_invoice_line inv_line on inv_line.invoice_id = inv.id
                left join product_product prod on prod.id = inv_line.product_id
                left join product_template templ on templ.id = prod.product_tmpl_id
                inner join res_partner part on part.id = inv.partner_id
                left join account_invoice_line_tax line_tax on line_tax.invoice_line_id = inv_line.id and line_tax.tax_id in %s
                left join account_invoice_line_tax line_tax2 on line_tax2.invoice_line_id = inv_line.id
                left join account_tax line_tax2_account_tax on line_tax2.tax_id = line_tax2_account_tax.id
                where inv.date_invoice between %s and %s
                and inv.company_id = %s
                and inv.type in ('out_invoice', 'out_refund')
                and inv.state in ('open', 'paid')
                and (country.intrastat = true or (inv.date_invoice <= '2020-12-31' and country.code = 'GB'))
                and country.id != %s
                and line_tax2_account_tax.code not in %s
                group by templ.acc_product_type, trade_type, country.code, part.vat, part.id''',
            (tuple(tax_ids), date_from, date_to, self.company_id.id, self.company_id.partner_id.country_id.id,
             tuple(pvm_exclude_codes))
        )
        r = self._cr.fetchall()
        # < type 'tuple' >: (17, u'product', u'BE', u'LT123456715', 60.0)
        data = []
        data_dict = {}
        rounding = self.company_id.currency_id.rounding
        partners_without_vats = []
        for row in r:
            if float_compare(row[4], 0, precision_rounding=rounding) == 0:
                continue
            if not row[3]:
                partners_without_vats.append((row[0]))
                if self.ignore_missing_vat:
                    continue
            if row[1] not in ['service', 'three_way']:
                type = 'product'
            elif row[1] == 'service':
                type = 'service'
            else:
                type = 'three_way'
            if row[0] in data_dict.keys():
                if type in data_dict[row[0]].keys():
                    data_dict[row[0]][type] += row[4]
                else:
                    data_dict[row[0]][type] = row[4]
            else:
                data_dict[row[0]] = {}
                if row[3] and len(row[3]) > 2:
                    data_dict[row[0]]['country_code'] = str(row[3][:2]).upper()
                else:
                    data_dict[row[0]]['country_code'] = row[2]
                data_dict[row[0]]['vat'] = row[3]
                data_dict[row[0]]['product'] = 0.0
                data_dict[row[0]]['service'] = 0.0
                data_dict[row[0]]['three_way'] = 0.0
                data_dict[row[0]][type] += row[4]
                data.append(data_dict[row[0]])
        if partners_without_vats and not self.ignore_missing_vat:
            msg = _('Šie partneriai neturi sukonfigūruoto PVM kodo:\n')
            for partner_id in set(partners_without_vats):
                partner = self.env['res.partner'].browse(partner_id)
                msg += partner.name + '\n'
            raise exceptions.UserError(msg)
        return data


FR0564()


class ISAF(models.TransientModel):
    _name = 'e.vmi.isaf'

    @api.multi
    def auto_load(self):
        if 'file' in self._context.keys():
            return self._context['file']
        else:
            return ''

    def _file_name(self):
        return 'iSAF.xml'

    def default_year(self):
        return (datetime.utcnow() - relativedelta(months=1)).year

    def default_month(self):
        return (datetime.utcnow() - relativedelta(months=1)).month

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id,
                                 required=True)
    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Year', default=default_year)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Month',
                             default=default_month)
    date_from = fields.Date(string='Nuo', required=True)
    date_to = fields.Date(string='Iki', required=True)
    filter = fields.Selection([('all', 'All invoices'),
                               ('sale', 'Customer invoices'),
                               ('purchase', 'Supplier invoices')], default='all', required=True)
    file = fields.Binary(string='Ataskaita', readonly=True, default=auto_load)
    file_name = fields.Char(string='Failo pavadinimas', default=_file_name)
    show_early_isaf_banner = fields.Boolean(compute='_compute_show_early_isaf_banner')

    @api.multi
    @api.depends('company_id')
    def _compute_show_early_isaf_banner(self):
        today = datetime.utcnow().day
        isaf_default_day = self.sudo().env.user.company_id.isaf_default_day
        for rec in self:
            rec.show_early_isaf_banner = True if today <= min(10, isaf_default_day or 19) else False

    @api.onchange('year', 'month')
    def onchange_date(self):
        if self.year and self.month:
            date_from = datetime(self.year, self.month, 1)
            date_to = date_from + relativedelta(day=31)
            self.date_from = date_from
            self.date_to = date_to

    @api.multi
    def open_isaf(self):
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_end = date_to + relativedelta(months=1, day=20)
        registration_start = date_to + relativedelta(day=21)
        date_from = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_start = registration_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_end = registration_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        domain = [('company_id', '=', self.company_id.id),
                  '|', '&', '&', '&', ('registration_date', '>=', date_from),
                  ('registration_date', '<=', registration_end),
                  ('date_invoice', '>=', date_from),
                  ('date_invoice', '<=', date_to),
                  '&', '&',
                  ('date_invoice', '<', date_from),
                  ('registration_date', '>=', registration_start),
                  ('registration_date', '<=', registration_end),
                  ]
        if self.filter == 'sale':
            domain.append(('doc_type', '=', 'sale'))
        elif self.filter == 'purchase':
            domain.append(('doc_type', '=', 'purchase'))
        return {
            'name': _('i.SAF'),
            'view_type': 'form',
            'view_mode': 'tree,pivot',
            'res_model': 'i.saf',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': domain,
        }

    @api.multi
    def generate_isaf(self):
        msg = 'Šie partneriai neturi nurodytų valstybių:\n'
        show_message = False
        types = ['out_refund', 'out_invoice']

        company_data = self.company_id.get_report_company_data()
        if not company_data['vat_code']:
            raise exceptions.UserError(_('Nenurodytas įmonės PVM kodas.'))
        purchase, sale = self.get_invoice_data()
        if self.filter == 'sale':
            purchase = []
        elif self.filter == 'purchase':
            sale = []
        partner_ids = []

        if self.filter != 'purchase':
            drafts = self.env['account.invoice'].search([('state', '=', 'draft'),
                                                         ('type', 'in', types),
                                                         ('move_name', '!=', False),
                                                         ('date_invoice', '>=', self.date_from),
                                                         ('date_invoice', '<=', self.date_to)])
            if drafts:
                error = _('Negalima generuoti ISAF turint juodraštinių sąskaitų! Patvirtinkite šias sąskaitas:\n')
                for draft in drafts:
                    error += _("Sąskaitos numeris") + ": {0}\n".format(draft.move_name)
                raise exceptions.Warning(error)

        for inv_id, inv_data in enumerate(sale + purchase):
            if not inv_data['country_code'] and inv_data['partner'] not in partner_ids:
                partner_ids.append(inv_data['partner'])
                show_message = True
                msg += inv_data['partner'] + '\n'
        if not purchase and not sale:
            raise exceptions.UserError(_('Nerasta tinkamų sąskaitų pasirinktam periodui'))
        if show_message:
            raise exceptions.UserError(msg)
        if self.filter == 'all':
            data_type = 'F'
        elif self.filter == 'sale':
            data_type = 'S'
        else:
            data_type = 'P'
        xml = Element('iSAFFile')

        xml.attrib['xmlns:xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
        xml.attrib['xmlns:doc'] = 'https://www.vmi.lt/cms/isaf/dokumentacija'
        xml.attrib['xmlns'] = 'http://www.vmi.lt/cms/imas/isaf'

        SubElement(xml, 'Header')
        SubElement(xml[0], 'FileDescription')
        SubElement(xml[0][0], 'FileVersion')
        xml[0][0][0].text = 'iSAF1.2'
        SubElement(xml[0][0], 'FileDateCreated')
        xml[0][0][1].text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')  # tools.DEFAULT_SERVER_DATE_FORMAT
        SubElement(xml[0][0], 'DataType')
        xml[0][0][2].text = data_type
        SubElement(xml[0][0], 'SoftwareCompanyName')
        xml[0][0][3].text = 'UAB Robolabs'
        SubElement(xml[0][0], 'SoftwareName')
        xml[0][0][4].text = 'Robo'
        SubElement(xml[0][0], 'SoftwareVersion')
        xml[0][0][5].text = '1.0'
        SubElement(xml[0][0], 'RegistrationNumber')
        xml[0][0][6].text = company_data['code'][:35]
        SubElement(xml[0][0], 'NumberOfParts')
        xml[0][0][7].text = str(1)
        SubElement(xml[0][0], 'PartNumber')
        xml[0][0][8].text = 'FULL'
        SubElement(xml[0][0], 'SelectionCriteria')

        # month_days = calendar.monthrange(self.year, self.month)[1]
        # date_from = datetime(year=self.year, month=self.month, day=1)
        # date_to = datetime(year=self.year, month=self.month, day=month_days)

        SubElement(xml[0][0][9], 'SelectionStartDate')
        xml[0][0][9][0].text = self.date_from
        SubElement(xml[0][0][9], 'SelectionEndDate')
        xml[0][0][9][1].text = self.date_to

        SubElement(xml, 'SourceDocuments')

        if purchase:
            purchase_el = SubElement(xml[1], 'PurchaseInvoices')
            p_invoice_idx = 0 if xml[1][0] == purchase_el else 1  # in case of no purchase invoices
        for idx, p_invoice in enumerate(purchase):
            p_inv = SubElement(xml[1][p_invoice_idx], 'Invoice')
            self.prepare_inv_info(p_inv, p_invoice, 'purchase')

        if sale:
            sale_el = SubElement(xml[1], 'SalesInvoices')
            sale_invoice_idx = 0 if xml[1][0] == sale_el else 1  # in case of no purchase invoices
        for idx, s_invoice in enumerate(sale):
            s_inv = SubElement(xml[1][sale_invoice_idx], 'Invoice')
            self.prepare_inv_info(s_inv, s_invoice, 'sale')

        u = tostring(xml, encoding="UTF-8")
        u = etree.fromstring(u)
        u = etree.tostring(u, encoding="UTF-8", xml_declaration=True)
        file = parseString(u).toprettyxml(encoding='UTF-8')

        if not xml_validator(file, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/isaf_1.2.xsd'):
            raise exceptions.Warning(_('Nepavyko sugeneruoti iSAF xml failo'))

        if self._context.get('isaf', False):
            result = self.env.user.upload_isaf(file.encode('base64'), self.date_from)
            if not result:
                raise exceptions.UserError(_('Nepavyko įkelti rinkmenos.'))
        attach_vals = {'res_model': 'res.company',
                       'name': self.file_name,
                       'datas_fname': self.file_name,
                       'res_id': self.company_id.id,
                       'type': 'binary',
                       'datas': file.encode('base64')}
        self.env['ir.attachment'].sudo().create(attach_vals)
        # --------------------------------------
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.isaf',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_isaf_download').id,
            'context': {'file': file.encode('base64')},
        }

    def prepare_inv_info(self, invoice_el, inv_data, type):
        SubElement(invoice_el, 'InvoiceNo')
        invoice_el[0].text = inv_data['invoice_no']
        if type == 'purchase':
            partner = 'SupplierInfo'
            partner_id = 'SupplierID'
        elif type == 'sale':
            partner = 'CustomerInfo'
            partner_id = 'CustomerID'
        else:
            raise exceptions.UserError(_('Wrong type'))
        partner_info = SubElement(invoice_el, partner)
        el_partner_id = SubElement(partner_info, partner_id)
        el_partner_id.text = str(inv_data['partner_id'])

        el_partner_VATRegistrationNumber = SubElement(partner_info, 'VATRegistrationNumber')
        el_partner_VATRegistrationNumber.text = str(inv_data['vat'])

        el_partner_RegistrationNumber = SubElement(partner_info, 'RegistrationNumber')
        el_partner_RegistrationNumber.text = str(inv_data['partner_code'])[:35]

        el_partner_country = SubElement(partner_info, 'Country')
        el_partner_country.text = str(inv_data['country_code'])

        el_partner_name = SubElement(partner_info, 'Name')
        el_partner_name.text = str(inv_data['partner'])

        el_invoice_date = SubElement(invoice_el, 'InvoiceDate')
        el_invoice_date.text = inv_data['invoice_date']

        el_invoice_type = SubElement(invoice_el, 'InvoiceType')
        el_invoice_type.text = inv_data['inv_type']

        el_SpecialTaxation = SubElement(invoice_el, 'SpecialTaxation')
        el_SpecialTaxation.text = inv_data['special_taxation']

        SubElement(invoice_el, 'References')

        el_VATPointDate = SubElement(invoice_el, 'VATPointDate')
        el_VATPointDate.text = inv_data['VATPointDate']

        if type == 'purchase':
            el_RegistrationAccountDate = SubElement(invoice_el, 'RegistrationAccountDate')
            el_RegistrationAccountDate.text = inv_data['VATPointDate']

        doc_totals = SubElement(invoice_el, 'DocumentTotals')
        for tax_idx, tax in enumerate(inv_data['document_total']):
            # if tax['tax_code'] in ['PVM5', 'PVM36', 'PVM29', 'PVM47', 'PVM42', 'PVM39']:
            #     continue

            SubElement(doc_totals, 'DocumentTotal')

            el_taxable_value = SubElement(doc_totals[tax_idx], 'TaxableValue')
            el_taxable_value.text = "%.2f" % tax['taxable_value'] if tax['taxable_value'] else "0.00"

            el_tax_code = SubElement(doc_totals[tax_idx], 'TaxCode')
            el_tax_code.text = tax['tax_code']
            taxpercentage_el = SubElement(doc_totals[tax_idx], 'TaxPercentage')
            if tax['tax_code'] in ['PVM5', 'PVM29', 'PVM15', 'PVM34', 'PVM36', 'PVM19', 'PVM39', 'PVM42', 'PVM47',
                                   'PVM48']:
                taxpercentage_el.attrib['xsi:nil'] = 'true'
            else:
                tax_percentage = "%.2f" % tax['tax_percentage'] if tax['tax_percentage'] else "0"
                taxpercentage_el.text = tax_percentage

            amount_el = SubElement(doc_totals[tax_idx], 'Amount')
            amount_el.text = "%.2f" % tax['amount'] if tax['amount'] else "0.00"

            if type == 'sale':
                VATPointDate2_el = SubElement(doc_totals[tax_idx], 'VATPointDate2')
                VATPointDate2_el.text = inv_data['VATPointDate']

    def get_invoice_data(self):
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        registration_end = date_to + relativedelta(months=1, day=20)
        registration_start = date_to + relativedelta(day=21)

        # PVM_taxes = self.env['account.tax'].search([('code', '=ilike', 'PVM%'),
        #                                             ('code', 'not in', ['PVM24']),
        #                                             # ('code', 'not in', ['PVM5', 'PVM36', 'PVM29', 'PVM47', 'PVM42', 'PVM39'])
        #                                             ])
        # tax_ids = PVM_taxes.mapped('id')
        # if not tax_ids:
        #     tax_ids = [-1]
        self._cr.execute(
            '''
            select
                    invoice_id,
                    name,
                    vat,
                    kodas,
                    inv_number,
                    country_code,
                    date_invoice,
                    doc_type,
                    inv_type,
                    special_taxation,
                    operacijos_data,
                    taxable_value,
                    tax_code,
                    tax_percentage,
                    amount,
                    partner_id,
                    vatpointdate2,
                    registration_date
                FROM i_saf
                WHERE ((registration_date between %s AND %s AND date_invoice BETWEEN %s AND %s) OR (registration_date BETWEEN %s AND %s AND date_invoice < %s))
                    and company_id = %s
                order by doc_type''',
            (date_from, registration_end, date_from, date_to, registration_start, registration_end,
             date_from, self.company_id.id))
        purchase_invoices = []
        sale_invoices = []
        settlement_invoices = []
        data_dict = {}
        for row in self._cr.dictfetchall():
            invoice_id = row['invoice_id']
            tax_info = {}
            tax_info['taxable_value'] = row['taxable_value']
            tax_info['tax_code'] = row['tax_code']
            tax_info['tax_percentage'] = row['tax_percentage']
            tax_info['amount'] = row['amount']
            if invoice_id not in data_dict.keys():
                inv_data = data_dict.setdefault(invoice_id, {})
                inv_data['partner'] = row['name'].strip() if type(row['name']) in [str, unicode] else ''
                inv_data['vat'] = type(row['vat']) in [str, unicode] and row['vat'].strip() or 'ND'
                inv_data['partner_code'] = type(row['kodas']) in [str, unicode] and row['kodas'].strip() or 'ND'
                inv_data['invoice_no'] = row['inv_number'].strip() if type(row['inv_number']) in [str, unicode] else ''
                # if row[5] is None:
                #     raise exceptions.UserError(
                #         _("Partner %s of invoice '%s' has no country assigned." % (row[1], row[4])))
                inv_data['country_code'] = row['country_code']
                inv_data['invoice_date'] = row['operacijos_data']
                inv_data['doc_type'] = row['doc_type']
                inv_data['inv_type'] = row['inv_type']
                inv_data['special_taxation'] = row['special_taxation']
                inv_data['VATPointDate'] = row['date_invoice']
                inv_data['partner_id'] = row['partner_id']
                inv_data['registration_date'] = row['registration_date']
                # registration date cannot be earlier than invoice date
                if inv_data['registration_date'] < inv_data['invoice_date']:
                    inv_data['registration_date'] = inv_data['invoice_date']
                if inv_data['doc_type'] == 'purchase':
                    purchase_invoices.append(inv_data)
                elif inv_data['doc_type'] == 'sale':
                    sale_invoices.append(inv_data)
                else:
                    settlement_invoices.append(inv_data)
            else:
                inv_data = data_dict[invoice_id]
            inv_data.setdefault('document_total', []).append(tax_info)
        return purchase_invoices, sale_invoices


ISAF()


class iSAF(models.Model):
    _name = 'i.saf'
    _auto = False
    _order = 'date_invoice'

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita')
    name = fields.Char(string='Partneris')
    vat = fields.Char(string='PVM')
    kodas = fields.Char(string='Įmonės kodas')
    country_code = fields.Char(string='Valstybė')
    date_invoice = fields.Date(string='Data')
    operacijos_data = fields.Date(string='Išrašymo data')
    registration_date = fields.Date(string='Dokumento gavimo data')
    inv_number = fields.Char(string='Sąskaitos numeris')
    inv_type = fields.Char(string='Tipas')
    taxable_value = fields.Float(string='Suma be PVM')
    tax_percentage = fields.Float(string='PVM (%)')
    amount = fields.Float(string='PVM suma')
    total = fields.Float(string='Suma su PVM')
    tax_code = fields.Char(string='Mokesčių kodas')
    doc_type = fields.Char(string='Dokumento tipas')
    company_id = fields.Many2one('res.company', string='Kompanija')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'i_saf')
        self._cr.execute('''
        CREATE OR REPLACE VIEW i_saf AS (
        select
          ROW_NUMBER() OVER (ORDER BY tax_code, invoice_id, tax_percentage) AS id,
          invoice_id,
          name,
          vat,
          kodas,
          country_code,
          inv_number,
          special_taxation,
          date_invoice,
          doc_type,
          inv_type,
          tax_percentage,
          taxable_value,
          amount,
          total,
          partner_id,
          company_id,
          vatpointdate2,
          tax_code,
          operacijos_data,
          registration_date
          FROM (
          select
                    inv.id as invoice_id,
                    CASE when part.name is null then parent.name else part.name end as name,
                    CASE WHEN part.vat is not NULL then part.vat else 'ND' end as vat,
                    CASE WHEN part.kodas is not NULL then part.kodas else 'ND' end as kodas,
                    CASE WHEN inv.type = 'out_refund' AND inv.state <> 'cancel' THEN inv.number
                         WHEN inv.reference is not NULL and inv.type in ('in_invoice', 'in_refund') THEN inv.reference
                         ELSE inv.move_name END as inv_number,
                    country.code as country_code,
                    inv.date_invoice,
                    CASE WHEN inv.type = 'out_invoice' or inv.type = 'out_refund' THEN 'sale'
                        ELSE CASE WHEN inv.type = 'in_invoice' or inv.type = 'in_refund' THEN 'purchase' ELSE inv.type END END as doc_type,
                    CASE WHEN inv.state = 'cancel' then 'AN'
                        ELSE CASE inv.type
                            WHEN 'out_refund' THEN 'KS'
                            WHEN 'in_refund' THEN 'KS'
                            WHEN 'in_invoice' THEN 'SF'
                            WHEN 'out_invoice' THEN 'SF' END END as inv_type,
                    false as special_taxation,
                    inv.date_invoice as VATPointDate,
                    CASE when inv.type like '%%_refund' then -SUM(abs(inv_tax.base_signed)) else SUM(abs(inv_tax.base_signed)) end as taxable_value,
                    tax.code as tax_code,
                    abs(tax.amount) as tax_percentage,
                    CASE WHEN inv.type LIKE '%%_refund' THEN -SUM(abs(inv_tax.amount_signed)) ELSE SUM(abs(inv_tax.amount_signed)) END as amount,
                    CASE WHEN inv.type LIKE '%%_refund' THEN -SUM(abs(inv_tax.amount_signed) + abs(inv_tax.base_signed)) WHEN inv.type LIKE '%%_invoice' THEN SUM(abs(inv_tax.amount_signed) + abs(inv_tax.base_signed)) END as total,
                    part.id as partner_id,
                    inv.company_id,
                    '1900-01-01'::date as vatpointdate2,
                    inv.operacijos_data,
                    inv.registration_date
                from account_invoice inv
                    inner join res_partner part on part.id = inv.partner_id
                    left join res_country country on country.id = part.country_id
                    inner join account_invoice_tax inv_tax on inv.id = inv_tax.invoice_id
                    inner join account_tax tax on inv_tax.tax_id = tax.id
                    left join res_partner parent on parent.id = part.parent_id
                where (inv.state IN ('open', 'paid') OR inv.type IN ('out_invoice', 'out_refund') AND inv.move_name IS NOT NULL AND inv.state = 'cancel') and tax.code like 'PVM%%' and tax.code != 'PVM24' AND COALESCE(inv.skip_isaf, false) = false
                group by country.code, inv.date_invoice, inv.type, part.vat, part.id, inv.number, tax.code, tax.amount, inv.id, parent.name
                ) as foo
        )
        ''', ())


iSAF()
