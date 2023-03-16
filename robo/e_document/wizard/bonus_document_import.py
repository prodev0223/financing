# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

import openpyxl as px
from dateutil.relativedelta import relativedelta
from six import iteritems

from odoo import models, api, fields, exceptions, _, tools
from odoo.addons.robo.wizard.robo_company_settings import convert_to_string

import_header_mapping = {
    u'Premijos rūšis': 'bonus_type_selection',
    u'Skaičiuojama': 'bonus_input_type',
    u'Laikotarpio, už kurį skiriama, pradžia ': 'date_from',
    u'Laikotarpio, už kurį skiriama, pabaiga ': 'date_to',
    u'Mėnesio, su kurio darbo užmokesčiu išmokėti, pirma diena ': 'payment_date',
    u'Darbuotojo(-s) Vardas, Pavardė': 'employee_name',
    u'Darbuotojo(-s) Asmens kodas': 'employee_identification',
    u'Priedo dydis': 'amount',
}


def import_bonus_documents(self, file_to_import):
    return self.import_bonus_documents(file_to_import)


class BonusDocumentImport(models.TransientModel):
    _name = 'bonus.document.import'
    _inherit = 'e.document.import'

    group_documents = fields.Boolean('Group documents (creates one document for multiple employees)', default=True)

    @api.multi
    def import_document(self):
        self.ensure_one()
        super(BonusDocumentImport, self).import_document()
        return self.threaded_import_prep('import_bonus_documents', self.file_to_import, import_bonus_documents)

    @api.model
    def process_bonus_type(self, bonus_type_selection):
        """ Checks if the bonus type is provided and matches one of the selection field values"""
        if not bonus_type_selection:
            raise exceptions.UserError(_('Bonus type not specified'))

        # Process bonus type from selection title to selection value
        # Get selection values with forced language since the import is in lithuanian
        selection_values = self.env['e.document'].with_context(lang='lt_LT')._fields['bonus_type_selection'].selection
        matched_selection = None
        for selection_value in selection_values:
            # Check if selection string matches
            if bonus_type_selection == selection_value[1]:
                matched_selection = selection_value
                break
        if not matched_selection:
            raise exceptions.UserError(_('Incorrect bonus type selected'))
        bonus_type_selection = matched_selection[0]

        return bonus_type_selection

    @api.model
    def process_bonus_input_type(self, bonus_type_selection, bonus_input_type):
        """
        Checks if the bonus input type is provided, matches one of the selection field values and is allowed for the
        given bonus type selection
        """
        if not bonus_input_type:
            raise exceptions.UserError(_('Bonus input type not specified'))
            # Get selection values with forced language since the import is in lithuanian

        # Process bonus input type from selection title to selection value
        # Get selection values with forced language since the import is in lithuanian
        selection_values = self.env['e.document'].with_context(lang='lt_LT')._fields['bonus_input_type'].selection
        matched_selection = None
        for selection_value in selection_values:
            # Check if selection string matches
            if bonus_input_type == selection_value[1]:
                matched_selection = selection_value
                break
        if not matched_selection:
            raise exceptions.UserError(_('Incorrect bonus input type selected'))
        bonus_input_type = matched_selection[0]

        # Only allow neto selection if bonus type is monthly or non vdu
        if bonus_type_selection not in ('1men', 'ne_vdu') and bonus_input_type == 'neto':
            raise exceptions.ValidationError(
                _('Specifying NET amount is only allowed for "Monthly" or "Non-VDU" bonuses')
            )

        return bonus_input_type

    @api.model
    def process_dates(self, bonus_type_selection, date_from, date_to, payment_date):
        """
        Checks if the dates match the constraints based on bonus type selection and if they are correctly set as first
        and last day of specific period
        :param bonus_type_selection: (str) bonus type
        :param date_from: (datetime) period date from
        :param date_to: (datetime) period date to
        :param payment_date: (datetime) payment date
        :return date_from (str), date_to (str), payment_date (str)
        """
        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        try:
            date_from_str = date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            raise exceptions.UserError(_('Could not parse period date from'))
        try:
            date_to_str = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            raise exceptions.UserError(_('Could not parse period date to'))
        try:
            payment_date_str = payment_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            raise exceptions.UserError(_('Could not parse period date to'))

        first_of_month_date_from = date_from + relativedelta(day=1)
        first_of_month_date_from_str = _strf(first_of_month_date_from)

        first_of_month_payment_date = payment_date + relativedelta(day=1)
        first_of_month_payment_date_str = _strf(first_of_month_payment_date)

        last_of_month_date_to = date_to + relativedelta(day=31)
        last_of_month_date_to_str = _strf(last_of_month_date_to)

        # Ensure the dates are the start and end of the month
        if bonus_type_selection in ('1men', '3men'):
            if date_from_str != first_of_month_date_from_str:
                raise exceptions.UserError(_('Period date from must be the first day of the month'))
            if date_to_str != last_of_month_date_to_str:
                raise exceptions.UserError(_('Period date to must be the last day of the month'))

        # Ensure that the period duration is as expected
        if bonus_type_selection == '1men':
            end_of_month_based_on_date_from = _strf(date_from + relativedelta(day=31))
            if date_to_str != end_of_month_based_on_date_from:
                raise exceptions.ValidationError(
                    _('When choosing monthly bonus type - the period must be a single month')
                )
        if bonus_type_selection == '3men':
            end_of_month_based_on_date_from = _strf(date_from + relativedelta(months=2, day=31))
            if date_to_str != end_of_month_based_on_date_from:
                raise exceptions.ValidationError(
                    _('When choosing quarterly bonus type - the period must be exactly 3 months')
                )

        if payment_date_str != first_of_month_payment_date_str:
            raise exceptions.ValidationError(_('Payment date must be the first date of the month'))

        return date_from_str, date_to_str, payment_date_str

    @api.model
    def process_and_validate_import_data(self, record, **kwargs):
        """ Processes and validates import record. Returns a dictionary containing the record objects """
        # Assign data to variables
        employee_name = convert_to_string(record.employee_name)
        employee_identification = convert_to_string(record.employee_identification)
        bonus_type_selection = convert_to_string(record.bonus_type_selection)
        bonus_input_type = convert_to_string(record.bonus_input_type)

        # Process data
        bonus_type_selection = self.process_bonus_type(bonus_type_selection)
        bonus_input_type = self.process_bonus_input_type(bonus_type_selection, bonus_input_type)
        employee = self.find_employee(employee_name, employee_identification)
        amount = self.process_amount(record.amount)

        # Check and process the dates
        date_from, date_to, payment_date = self.process_dates(bonus_type_selection, record.date_from, record.date_to,
                                                              record.payment_date)

        # Return processed data
        return {
            'employee': employee,
            'bonus_type_selection': bonus_type_selection,
            'bonus_input_type': bonus_input_type,
            'amount': amount,
            'date_from': date_from,
            'date_to': date_to,
            'payment_date': payment_date,
        }

    @api.model
    def create_bonus_documents(self, records_by_document, auto_confirm=False):
        """
        Creates bonus documents based on the records provided
        :param records_by_document: (list) List of records for each document
        :param auto_confirm: (bool) Should the documents be confirmed
        """
        bonus_order_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        for records_for_document in records_by_document:
            # Determine document values from the first record
            payment_date, date_from, date_to, bonus_input_type, bonus_type_selection = [
                records_for_document[0][key]
                for key in ['payment_date', 'date_from', 'date_to', 'bonus_input_type', 'bonus_type_selection']
            ]

            # Determine eDocument line values
            e_document_line_values = list()
            for record in records_for_document:
                employee = record['employee']
                amount = record['amount']
                e_document_line_values.append((0, 0, {
                    'employee_id2': employee.id,
                    'float_1': amount
                }))

            # Create document
            document = self.env['e.document'].sudo().create({
                'template_id': bonus_order_template.id,
                'document_type': 'isakymas',
                'date_1': date_from,
                'date_2': date_to,
                'date_3': payment_date,
                'date_document': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'e_document_line_ids': e_document_line_values,
                'bonus_type_selection': bonus_type_selection,
                'bonus_input_type': bonus_input_type
            })
            self.env['hr.payroll'].sudo().reload_document(document, confirm=auto_confirm)

    @api.multi
    def import_bonus_documents(self, file_to_import):
        self.ensure_one()

        # Load file and the workbook
        file_to_import = io.BytesIO(base64.decodestring(file_to_import))
        workbook = px.load_workbook(file_to_import)
        sheet = workbook['Priedo skyrimas']

        # Parse rows
        rows = iter(sheet.iter_rows())
        parsed_rows = self.process_worksheet_data(rows, import_header_mapping)

        # Group records if necessary
        if self.group_documents:
            records_by_key = dict()
            for record in parsed_rows:
                # Generate a key to group the record by
                key_attributes = ['bonus_input_type', 'bonus_type_selection', 'date_from', 'date_to', 'payment_date']
                key = '/'.join(['{}'] * len(key_attributes)).format(*[record[key] for key in key_attributes])
                if key not in records_by_key:
                    records_by_key[key] = [record]
                else:
                    records_by_key[key].append(record)
            records_by_document = [values for key, values in iteritems(records_by_key)]
        else:
            records_by_document = [[record] for record in parsed_rows]

        # Create documents
        self.create_bonus_documents(records_by_document, self.auto_confirm)
