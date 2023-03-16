# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

import openpyxl as px

from odoo import models, api, fields, exceptions, _, tools
from odoo.addons.robo.wizard.robo_company_settings import convert_to_string

import_header_mapping = {
    u'Pervedimo data': 'payment_date',
    u'Darbuotojo(-s) Vardas Pavardė': 'employee_name',
    u'Darbuotojo(-s) asmens kodas': 'employee_identification',
    u'Pervedimo suma': 'amount',
    u'Pensijų fondo pavadinimas': 'fund_name',
    u'Pensijų fondo kodas': 'fund_code',
}


def import_pension_transfer_document(self, file_to_import):
    return self.import_pension_transfer_document(file_to_import)


class PensionFundTransferDocumentImport(models.TransientModel):
    _name = 'pension.fund.transfer.document.import'
    _inherit = 'e.document.import'

    group_by_date = fields.Boolean('Group by date (creates one document for multiple employees)', default=True)
    assign_pension_funds_to_employees = fields.Boolean('Assign pension funds to employees', default=False)
    create_missing_pension_funds = fields.Boolean('Create missing pension funds', default=False)

    @api.multi
    def import_document(self):
        self.ensure_one()
        super(PensionFundTransferDocumentImport, self).import_document()
        return self.threaded_import_prep('import_pension_fund_transfers', self.file_to_import,
                                         import_pension_transfer_document)

    @api.model
    def find_pension_fund(self, name, code, create_missing_pension_funds=False):
        """
        Finds pension fund by provided name and/or fund code
        :param name: (str) Pension fund's name
        :param code: (str) Pension fund's code
        :param create_missing_pension_funds: (bool) If pension fund is not found - should it be created
        :return: (res.pension.fund) Pension fund
        """
        ResPensionFund = self.env['res.pension.fund'].sudo()
        pension_fund = ResPensionFund
        if code:
            pension_fund = ResPensionFund.search([('fund_code', '=', code)])
        if not pension_fund and name:
            pension_fund = ResPensionFund.search([('name', '=', name)])
        if not pension_fund and create_missing_pension_funds:
            if not code or not name:
                raise exceptions.UserError(_('Could not create pension fund: missing fund name or fund code'))
            pension_fund = ResPensionFund.create({'name': name, 'fund_code': code})
        if not pension_fund:
            raise exceptions.UserError(_('Could not find pension fund'))
        if len(pension_fund) > 1:
            raise exceptions.UserError(_('Multiple pension funds found'))
        return pension_fund

    @api.model
    def process_and_validate_import_data(self, record, **kwargs):
        """ Processes and validates import record. Returns a dictionary containing the record objects """
        create_missing_pension_funds = kwargs.get('create_missing_pension_funds')

        employee_name = convert_to_string(record.employee_name)
        employee_identification = convert_to_string(record.employee_identification)
        fund_name = convert_to_string(record.fund_name)
        fund_code = convert_to_string(record.fund_code)
        payment_date = record.payment_date

        # Check for payment date
        if not payment_date:
            raise exceptions.UserError(_('Payment date not specified'))

        # Find the employee
        employee = self.find_employee(employee_name, employee_identification)

        # Get the pension fund
        pension_fund = self.find_pension_fund(fund_name, fund_code, create_missing_pension_funds)

        # Process the amount
        amount = self.process_amount(record.amount)

        return {
            'employee': employee,
            'pension_fund': pension_fund,
            'amount': amount,
            'payment_date': payment_date
        }

    @api.model
    def create_pension_fund_transfer_documents(self, records_by_document, assign_pension_funds_to_employees=False,
                                               auto_confirm=False):
        """ Creates pension fund documents based on the records specified """
        pension_payment_order_template = self.env.ref('e_document.pension_payment_order_template')
        for records_for_document in records_by_document:
            payment_date = records_for_document[0]['payment_date']

            document = self.env['e.document'].sudo().create({
                'template_id': pension_payment_order_template.id,
                'document_type': 'isakymas',
                'date_1': payment_date,
                'date_document': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            })

            for record in records_for_document:
                employee = record['employee']
                pension_fund = record['pension_fund']
                if assign_pension_funds_to_employees and not employee.pension_fund_id:
                    employee.write({'pension_fund_id': pension_fund.id})
                amount = record['amount']

                line = self.env['e.document.line'].create({
                    'employee_id2': employee.id,
                    'pension_fund_id': pension_fund.id,
                    'float_1': amount,
                    'e_document_id': document.id
                })
                if not line.pension_fund_id:
                    line.pension_fund_id = pension_fund.id

            self.env['hr.payroll'].sudo().reload_document(document, confirm=auto_confirm)

    @api.multi
    def import_pension_transfer_document(self, file_to_import):
        self.ensure_one()

        # Load file and the workbook
        file_to_import = io.BytesIO(base64.decodestring(file_to_import))
        workbook = px.load_workbook(file_to_import)
        sheet = workbook['Pervedimai į pensijų fondus']

        # Parse rows
        rows = iter(sheet.iter_rows())
        parsed_rows = self.process_worksheet_data(
            rows, import_header_mapping, create_missing_pension_funds=self.create_missing_pension_funds
        )

        # Group records if necessary
        if self.group_by_date:
            payment_dates = set(record['payment_date'] for record in parsed_rows)
            records_by_document = [
                [record for record in parsed_rows if record['payment_date'] == payment_date]
                for payment_date in payment_dates
            ]
        else:
            records_by_document = [[record] for record in parsed_rows]

        # Create documents
        self.create_pension_fund_transfer_documents(records_by_document, self.assign_pension_funds_to_employees,
                                                    self.auto_confirm)
