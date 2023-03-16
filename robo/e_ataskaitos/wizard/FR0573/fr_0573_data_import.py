# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from xlrd import XLRDError
from datetime import datetime
from six import iteritems

FIELD_MAPPING = {
    'date': 'Įrašo data',
    'document_name': 'Kilmės dokumentas',
    'document_type': 'Dokumento tipas',
    'employee_code': 'Identifikacinis numeris',
    'employee_code_type': 'Identifikacinio numerio tipas',
    'employee_name': 'Vardas, pavardė',
    'a_class_code': 'A klasės kodas',
    'b_class_code': 'B klasės kodas',
    'employer_payout': 'Darbdavio išmoka',
    'payout_amount': 'Išmokos suma',
    'gpm_amount': 'GPM suma',
    'gpm_for_responsible_person_amount': 'Išmokas išmokėjusio asmens lėšomis sumokėta GPM suma',
    'country_code': 'Užsienio valstybės kodas',
    'foreign_paid_gpm_amount': 'Užsienio valstybėje sumokėta GPM suma',
}

FIELD_LIST = ['date', 'document_name', 'document_type', 'employee_code',
              'employee_code_type', 'employee_name', 'a_class_code', 'b_class_code', 'employer_payout',
              'payout_amount', 'gpm_amount', 'gpm_for_responsible_person_amount', 'country_code',
              'foreign_paid_gpm_amount']

REQUIRED_FIELD_MAPPING = ['date', 'document_type', 'employee_code', 'employee_code_type',
                          'employee_name', 'payout_amount']

FLOAT_MAPPING = ['gpm_amount', 'gpm_for_responsible_person_amount', 'foreign_paid_gpm_amount']

STR_MAPPING = ['employee_code_type', 'a_class_code', 'b_class_code', 'employee_code', 'document_name']

BOOL_MAPPING = ['employer_payout']

EMPLOYEE_CODE_TYPE_MAPPING = {
    '1': 'mmak',
    '2': 'vlm',
    '3': 'PVMmk',
    '4': 'ivvpn',
    '5': 'atpdsin'
}

DOCUMENT_TYPE_MAPPING = {
    'Pagrindinis atlyginimas': 'payslip',
    'Avansas': 'advance',
    'Atostoginiai': 'holidays',
    'Dienpinigiai': 'allowance',
    'Natūra': 'natura',
    'Importuota': 'imported',
    'Kita': 'other',
    'Savom lėšom': 'own_expense'
}


class FR0573DataImport(models.TransientModel):

    _name = 'fr.0573.data.import'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)

    @api.multi
    def data_import(self):
        """
        Read data from XLS file and prepare it for further fr.0573.report creation
        :return: None
        """
        self.ensure_one()
        data = self.xls_data
        record_set = []

        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(data))
        except XLRDError:
            raise exceptions.UserError(_('Netinkamas failo formatas!'))
        sheet = wb.sheets()[0]
        for row in range(sheet.nrows):
            if row == 0:
                continue
            col = 0
            record = {'row_number': str(row + 1)}
            for field in FIELD_LIST:
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = False

                # Explicit checks
                if field in ['date'] and value:
                    try:
                        value = datetime(
                            *xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    except Exception as e:
                        raise exceptions.UserError(_('Netinkamas datos formatas | Eilutės nr: %s | Klaida %s') % (
                            e.args[0], str(row + 1)))

                # General required field checks
                if field in REQUIRED_FIELD_MAPPING and not value and not isinstance(value, (int, float)):
                    raise exceptions.UserError(
                        _('Nerasta reikšmė privalomam laukui: %s. | Eilutės nr: %s') % (
                            FIELD_MAPPING[field], str(row + 1)))

                record[field] = value
                col += 1

            self.float_converter(record)
            self.str_converter(record)
            self.bool_converter(record)
            self.validator(record)
            record_set.append(record)

        ids = []
        for record in record_set:
            record = self.create_record(record)
            ids.append(record.id)

        action = self.env.ref('e_ataskaitos.action_vmi_fr_0573_report').read()[0]
        action['domain'] = [('id', 'in', ids)]
        action['views'] = [(self.env.ref('e_ataskaitos.vmi_fr_0573_report_tree').id, 'tree')]

        return action

    @api.model
    def validator(self, data):
        """
        Validate whether passed data fields pass all of the constraints
        :param data: XLS data set
        :return: None
        """
        body = str()

        employee_code_type = EMPLOYEE_CODE_TYPE_MAPPING.get(data.get('employee_code_type'))
        if not employee_code_type:
            body += _('Nurodytas klaidingas identifikacinio numerio tipas\n')

        document_type = DOCUMENT_TYPE_MAPPING.get(data.get('document_type'))
        if not document_type:
            body += _('Nurodytas klaidingas dokumento tipas\n')

        if body:
            body += _('Įrašo kūrimo klaida | Eilutės nr: %s') % data.get('row_number')
            raise exceptions.UserError(body)

    @api.model
    def create_record(self, data):
        """
        Create fr.0573.report record from passed XLS data
        :param data: record data, dict()
        :return: created fr.0573.report record
        """
        partner = self.get_partner(data)

        a_code = data.get('a_class_code')
        b_code = data.get('b_class_code')
        foreign_country_code = data.get('country_code')

        a_klase_kodas_id = self.env['a.klase.kodas'].search([('code', '=', a_code)], limit=1).id if a_code else False
        b_klase_kodas_id = self.env['b.klase.kodas'].search([('code', '=', b_code)], limit=1).id if b_code else False

        if not a_klase_kodas_id and not b_klase_kodas_id:
            raise exceptions.UserError(_('Neteisingai nurodytas A arba B klasės kodas | Eilutės nr: %s') %
                                       data.get('row_number'))

        foreign_country_id = self.env['res.country'].search([('code', '=', foreign_country_code)], limit=1).id \
            if foreign_country_code else False

        record_values = {
            'correction': True,
            'date': data.get('date'),
            'partner_id': partner.id,
            'a_klase_kodas_id': a_klase_kodas_id,
            'b_klase_kodas_id': b_klase_kodas_id,
            'origin': data.get('document_name'),
            'document_type': DOCUMENT_TYPE_MAPPING.get(data.get('document_type')),
            'employer_payout': data.get('employer_payout'),
            'amount_bruto': data.get('payout_amount'),
            'amount_tax': data.get('gpm_amount'),
            'gpm_for_responsible_person_amount': data.get('gpm_for_responsible_person_amount'),
            'foreign_paid_gpm_amount': data.get('foreign_paid_gpm_amount'),
            'foreign_country_id': foreign_country_id,
        }

        try:
            fr0573_record = self.env['fr.0573.report'].create(record_values)
        except Exception as e:
            raise exceptions.UserError(
                _('Įrašo kūrimo klaida | Eilutės nr: %s | Klaidos pranešimas %s') % (
                    data.get('row_number'), e.args[0]))

        return fr0573_record

    @api.model
    def get_partner(self, data):
        """
        Search for related res.partner record, if not found, create one from passed data
        :param data: XLS data (dict)
        :return: res.partner (single record)
        """
        ResPartner = self.env['res.partner']
        ResCountry = self.env['res.country']
        name = data.get('employee_name')
        code = data.get('employee_code')

        partner = ResPartner.search([('name', '=', name)], limit=1)
        if not partner and code:
            partner = ResPartner.search([('kodas', '=', code)], limit=1)
        if not partner:
            partner_code = EMPLOYEE_CODE_TYPE_MAPPING.get(data.get('employee_code_type'))
            country_code = data.get('country_code')
            country = ResCountry.sudo().search([('code', '=', country_code)], limit=1)

            if not country:
                country = ResCountry.sudo().search([('code', '=', 'LT')], limit=1)
            try:
                partner_vals = {
                    'name': name,
                    'kodas': code,
                    'partner_code_type': partner_code,
                    'country_id': country.id,
                }
                partner = ResPartner.create(partner_vals)
            except Exception as exc:
                raise exceptions.UserError(
                    _('Klaida kuriant partnerį %s | Eilutės nr: %s') % (exc.args[0], data.get('row_number')))
        return partner

    @api.model
    def float_converter(self, data):
        """
        Convert passed data field values to float based on static value list
        :param data: XLS data set
        :return: None
        """
        for key, field in iteritems(data):
            if key in FLOAT_MAPPING:
                try:
                    data[key] = float(field or 0.0)
                except ValueError:
                    raise exceptions.ValidationError(
                        _('Klaidinga skaitinė reikšmė laukui %s | Eilutės nr: %s') % (
                            FIELD_MAPPING[key], data['row_number']))

    @api.model
    def str_converter(self, data):
        """
        Convert passed data field values to str based on static value list
        :param data: XLS data set
        :return: None
        """
        for key, field in iteritems(data):
            if key in STR_MAPPING and not isinstance(field, (str, unicode)):
                try:
                    data[key] = str(int(field))
                except ValueError:
                    try:
                        data[key] = str(field)
                    except ValueError:
                        raise exceptions.UserError(
                            _('Klaidinga reikšmė laukui %s | Eilutės nr: %s') % (
                                FIELD_MAPPING[key], data['row_number']))

    @api.model
    def bool_converter(self, data):
        """
        Convert passed data field values to bool based on static value list
        :param data: XLS data set
        :return: None
        """
        for key, field in iteritems(data):
            if key in BOOL_MAPPING and field:
                if not isinstance(field, (str, unicode)) or field.lower() not in ['taip', 'ne']:
                    raise exceptions.UserError(
                        _('Klaidinga reikšmė laukui %s | Eilutės nr: %s') % (
                            FIELD_MAPPING[key], data['row_number']))
                elif field.lower() == 'taip':
                    data[key] = True
                else:
                    data[key] = False


FR0573DataImport()
