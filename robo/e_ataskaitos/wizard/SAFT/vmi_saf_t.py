# -*- coding: utf-8 -*-
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions, _
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring
from lxml import etree
from ...e_vmi_tools import xml_validator, float_to_str, SAFT_DATA_TYPE, SAFT_ACCOUNT_TYPE_MAPPER, \
    SAFT_MOVEMENT_TYPE, SAFT_PRODUCTION_MOVEMENTS, SAFT_INVOICE_TYPE_MAPPER
import logging

_logger = logging.getLogger(__name__)
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
DESCRIPTION_MAX_LENGTH = 256
UNDEFINED_PARTNER_NAME = 'Nenustatytas partneris'


class SafT(models.TransientModel):
    _name = 'vmi.saf.t'

    @api.model
    def _default_generated_file(self):
        """
        Get generated file from the context
        :return: Generated file (binary)
        """
        return self._context.get('generated_xml', str())

    @api.model
    def _default_date_from(self):
        """
        Get default period start date
        :return: Start date (datetime)
        """
        return self.env.user.company_id.compute_fiscalyear_dates()['date_from'] + relativedelta(years=-1)

    @api.model
    def _default_date_to(self):
        """
        Get default period end date
        :return: End date (datetime)
        """
        return self.env.user.company_id.compute_fiscalyear_dates()['date_to'] + relativedelta(years=-1)

    date_from = fields.Date(string='Data nuo', required=True, default=_default_date_from)
    date_to = fields.Date(string='Data iki', required=True, default=_default_date_to)
    data_type = fields.Selection(SAFT_DATA_TYPE, string='Duomenų tipas', required=True, default='F')
    saf_t_tax_id = fields.Many2one('saf.t.tax.table', string='Pelno mokesčio tipas')

    generated_file = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=_default_generated_file)
    file_name = fields.Char(string='Failo pavadinimas', default='SAF-T.xml')
    entity = fields.Char(string='Rinkmena', default='ROBO')

    @api.model
    def validate_constraints(self):
        """
        Check constraints before generating report
        :return: None
        """
        accounts_missing_classifier = self.env['account.account'].search(
            [('saf_t_account_id', '=', False), ('is_view', '=', False), ('deprecated', '=', False)])
        if accounts_missing_classifier:
            raise exceptions.ValidationError(_('Šioms didžiosios knygos sąskaitoms nėra nurodyta SAF-T '
                                               'klasifikatoriaus sąskaita:\n %s') %
                                             (' '.join(accounts_missing_classifier.mapped('code'))))
        # Check for a partner created specifically for a fill-in of move lines with undefined partner
        ResPartner = self.env['res.partner']
        undefined_partner = ResPartner.search([('name', '=', UNDEFINED_PARTNER_NAME)], limit=1)
        if not undefined_partner:
            ResPartner.create({
                'name': UNDEFINED_PARTNER_NAME,
                'is_company': False,
                'customer': True,
                'supplier': True
            })

    @api.model
    def check_partner_type(self, partners, partner_type):
        """
        Check partners are set to be of customer/supplier type
        :param partners: Partners to check
        :param partner_type: customer/supplier
        :return: None
        """
        ResPartner = self.env['res.partner']
        no_type_partners = partners.filtered(lambda x: not x[partner_type])
        partner_type_name = ResPartner._fields[partner_type].string
        if no_type_partners:
            raise exceptions.ValidationError(_('Šiems partneriams nenustatytas tipas "%s":\n %s') %
                                             (partner_type_name, '\n'.join(no_type_partners.mapped('name'))))

    @api.multi
    def button_generate_saft(self):
        """
        Generate SAF-T, based on value stored in res.company determine
        whether to use threaded mode or not
        :return: Result of specified method
        """
        self.ensure_one()
        filename = 'SAF-T %s %s %s-%s' % (self.env.user.company_id.name, self.data_type, self.date_from, self.date_to)
        report = 'SAF-T'

        self.validate_constraints()
        if self.sudo().env.user.company_id.activate_threaded_front_reports:
            return self.env['robo.report.job'].generate_report(
                self, 'generate_saft_file', report, returns='base64', forced_name=filename, forced_extension='xml')
        return self.generate_saft()

    @api.model
    def generate_saft_file(self):
        """
        Generate file and return it encoded in base64 format
        :return: Generated file (base64)
        """
        generated_xml = self.generate_xml_report()

        u = tostring(generated_xml, encoding='UTF-8')
        u = etree.fromstring(u)
        u = etree.tostring(u, encoding='UTF-8', xml_declaration=True)
        generated_file = parseString(u).toprettyxml(encoding='UTF-8')

        if not xml_validator(generated_file, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '../..', 'xsd_schemas')) + '/saft_2.1.xsd'):
            raise exceptions.UserError(_('Nepavyko sugeneruoti i.SAF-T XML failo'))

        generated_file = generated_file.encode('base64')
        return generated_file

    @api.multi
    def generate_saft(self):
        """
        Generate SAF-T and return a form to download generated file. Used in non-threaded mode
        :return: A form to download generated file
        """
        self.ensure_one()
        generated_file = self.generate_saft_file()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'vmi.saf.t',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_saf_t_download_form').id,
            'context': {'generated_xml': generated_file},
        }

    """ Root XML structure """

    @api.model
    def generate_xml_report(self):
        """
        Generate SAF-T report based on data type - Root node
        :return: Fully generated XML
        """
        xml = Element('AuditFile')

        xml.attrib['xmlns'] = 'https://www.vmi.lt/cms/saf-t'
        xml.attrib['xmlns:xs'] = 'http://www.w3.org/2001/XMLSchema'
        xml.attrib['xmlns:doc'] = 'https://www.vmi.lt/cms/saf-t/dokumentacija'
        xml.attrib['xmlns:xsd'] = 'http://www.w3.org/2001/XMLSchema'
        self.get_system_header(xml)
        self.get_master_files(xml)
        self.get_general_ledger_entries(xml)
        self.get_source_documents(xml)
        return xml

    @api.multi
    def get_system_header(self, element):
        """
        Get system and client information
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        company = self.env.user.sudo().company_id
        findir = company.findir
        date = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        fiscal_year = company.compute_fiscalyear_dates(date=date)

        header = SubElement(element, 'Header')
        SubElement(header, 'AuditFileVersion').text = '2.01'
        SubElement(header, 'AuditFileCountry').text = 'LT'
        SubElement(header, 'AuditFileDateCreated').text = datetime.now().strftime(DATETIME_FORMAT)
        SubElement(header, 'SoftwareCompanyName').text = 'UAB Robolabs'
        SubElement(header, 'SoftwareID').text = 'Robo'
        SubElement(header, 'SoftwareVersion').text = '1.0'

        company_header = SubElement(header, 'Company')
        SubElement(company_header, 'RegistrationNumber').text = company.partner_id.kodas
        SubElement(company_header, 'Name').text = company.partner_id.name

        address = SubElement(company_header, 'Address')
        self.get_address_structure(address, company.partner_id)

        contact = SubElement(company_header, 'Contact')
        person = SubElement(contact, 'ContactPerson')
        self.get_person_name_structure(person, findir.partner_id)
        SubElement(contact, 'Telephone').text = findir.work_phone
        SubElement(contact, 'Email').text = findir.email

        company_bank_accounts = self.sudo().env['account.journal'].search(
            [('type', '=', 'bank'), ('show_on_dashboard', '=', True), ('display_on_footer', '=', True)])
        if company_bank_accounts:
            bank_account = SubElement(company_header, 'BankAccount')
        for company_bank_account in company_bank_accounts:
            self.get_bank_account_structure(bank_account, company_bank_account.bank_acc_number)

        SubElement(header, 'DefaultCurrencyCode').text = 'EUR'

        criteria = SubElement(header, 'SelectionCriteria')
        SubElement(criteria, 'SelectionStartDate').text = self.date_from
        SubElement(criteria, 'SelectionEndDate').text = self.date_to
        SubElement(criteria, 'PeriodStart').text = self.date_from
        SubElement(criteria, 'PeriodEnd').text = self.date_to

        SubElement(header, 'TaxAccountingBasis').text = 'P'
        SubElement(header, 'FiscalYearFrom').text = fiscal_year['date_from'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        SubElement(header, 'FiscalYearTo').text = fiscal_year['date_to'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        SubElement(header, 'Entity').text = self.entity
        SubElement(header, 'DataType').text = self.data_type
        SubElement(header, 'NumberOfParts').text = '1'
        SubElement(header, 'PartNumber').text = '1'

    @api.multi
    def get_master_files(self, element):
        """
        Get root node of MasterFiles
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        data_type = self.data_type
        master_files = SubElement(element, 'MasterFiles')
        if data_type in ['F', 'GL']:
            self.get_general_ledger_accounts(master_files)

        if data_type in ['F', 'GL', 'MG', 'SI', 'PI', 'PA']:
            self.get_partners(master_files, 'customer')

        self.get_partners(master_files, 'supplier')

        if data_type in ['F', 'GL', 'MG', 'SI', 'PI']:
            self.get_tax_table(master_files)

        if data_type in ['F', 'MG']:
            self.get_movement_type_table(master_files)

        if data_type in ['F', 'MG', 'SI', 'PI']:
            self.get_uom_table(master_files)
            self.get_products(master_files)
            self.get_physical_stock(master_files)

        if data_type in ['F', 'AS']:
            self.get_assets(master_files)

        if data_type in ['F', 'GL']:
            self.get_owners(master_files)

    @api.multi
    def get_general_ledger_entries(self, element):
        """
        Get root node of general ledger entries
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        if self.data_type not in ['F', 'GL']:
            return
        sub_element, number_of_entries, total_debit, total_credit = self.get_journals()
        if not number_of_entries:
            return
        general_ledger_entries = SubElement(element, 'GeneralLedgerEntries')
        SubElement(general_ledger_entries, 'NumberOfEntries').text = str(number_of_entries)
        SubElement(general_ledger_entries, 'TotalDebit').text = float_to_str(total_debit)
        SubElement(general_ledger_entries, 'TotalCredit').text = float_to_str(total_credit)
        general_ledger_entries.append(sub_element)

    @api.multi
    def get_source_documents(self, element):
        """
        Get root node of source documents
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        data_type = self.data_type
        if data_type == 'GL':
            return

        source_documents = SubElement(element, 'SourceDocuments')
        if data_type in ['F', 'SI']:
            self.get_invoices_total(source_documents, 'out')

        if data_type in ['F', 'PI']:
            self.get_invoices_total(source_documents, 'in')

        if data_type in ['F', 'PA']:
            self.get_payments_total(source_documents)

        if data_type in ['F', 'MG']:
            self.get_movement_of_goods_total(source_documents)

        if data_type in ['F', 'AS']:
            self.get_asset_transactions_total(source_documents)

    """ Children XML structure """
    """ MasterFiles node """

    @api.multi
    def get_general_ledger_accounts(self, element):
        """
        Get general ledger account information and opening/closing period balances
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        general_ledger_accounts = SubElement(element, 'GeneralLedgerAccounts')
        accounts = self.env['account.account'].search([])
        # One search, filtering out done later. Done correspondingly to the accounts selected
        move_lines = self.env['account.move.line'].search([('date', '<=', self.date_to),
                                                           ('account_id', 'in', accounts.mapped('id')),
                                                           ('move_id.state', '=', 'posted')])
        for account in accounts:
            account_element = SubElement(general_ledger_accounts, 'Account')
            SubElement(account_element, 'AccountID').text = account.code
            SubElement(account_element, 'AccountDescription').text = account.name
            SubElement(account_element, 'AccountTableID').text = account.saf_t_account_id.code
            SubElement(account_element, 'AccountTableDescription').text = account.saf_t_account_id.description
            account_type = SAFT_ACCOUNT_TYPE_MAPPER.get(account.user_type_id.with_context(lang='lt_LT').name, str())
            SubElement(account_element, 'AccountType').text = account_type or 'KT'
            # Filter out by account to get balance at the end of the period
            closing_lines = move_lines.filtered(lambda x: x.account_id.id == account.id)
            closing_balance = sum(x.balance for x in closing_lines)
            closing_node = 'Debit' if tools.float_compare(closing_balance, 0.0, precision_digits=2) >= 0 else 'Credit'
            # Filter lines already filtered by date to get balance at the start of the period
            opening_lines = closing_lines.filtered(lambda x: x.date < self.date_from)
            opening_balance = sum(x.balance for x in opening_lines)
            opening_node = 'Debit' if tools.float_compare(opening_balance, 0.0, precision_digits=2) >= 0 else 'Credit'
            SubElement(account_element, 'Opening' + opening_node + 'Balance').text = float_to_str(
                abs(opening_balance))
            SubElement(account_element, 'Closing' + closing_node + 'Balance').text = float_to_str(
                abs(closing_balance))

    @api.multi
    def get_partners(self, element, partner_type):
        """
        Get partners information by type
        :param element: XML node element
        :param partner_type: customer/supplier
        :return: None
        """
        self.ensure_one()
        partner_node = 'Customer' if partner_type == 'customer' else 'Supplier'
        invoice_node = 'Sales' if partner_type == 'customer' else 'Purchase'
        partners_element = SubElement(element, partner_node + 's')
        partners = self.env['res.partner'].search([(partner_type, '=', True)])
        MoveLine = self.env['account.move.line']
        invoice_types = ['out_invoice', 'out_refund'] if partner_type == 'customer' else ['in_invoice', 'in_refund']
        invoices = self.env['account.invoice'].search([
            ('type', 'in', invoice_types), ('state', '=', 'open'), ('date_invoice', '<', self.date_from)
        ])

        for partner in partners:
            partner_element = SubElement(partners_element, partner_node)
            self.get_company_structure(partner_element, partner)
            SubElement(partner_element, partner_node + 'ID').text = str(partner.id)
            SubElement(partner_element, 'SelfBillingIndicator').text = str()

            account = partner.property_account_receivable_id if partner_type == 'customer' \
                else partner.property_account_payable_id
            # Search to get balance at the end of the period
            closing_lines = MoveLine.search(
                [('date', '<=', self.date_to), ('partner_id', '=', partner.id), ('account_id', '=', account.id),
                 ('move_id.state', '=', 'posted')])
            closing_balance = sum(x.balance for x in closing_lines)
            closing_node = 'Debit' if tools.float_compare(closing_balance, 0.0, precision_digits=2) >= 0 else 'Credit'
            # Filter lines by date to get balance at the start of the period
            opening_lines = closing_lines.filtered(lambda x: x.date < self.date_from)
            opening_balance = sum(x.balance for x in opening_lines)
            opening_node = 'Debit' if tools.float_compare(opening_balance, 0.0, precision_digits=2) >= 0 else 'Credit'
            accounts_element = SubElement(partner_element, 'Accounts')
            SubElement(accounts_element, 'AccountID').text = account.code
            SubElement(accounts_element, 'Opening' + opening_node + 'Balance').text = float_to_str(
                abs(opening_balance))
            SubElement(accounts_element, 'Closing' + closing_node + 'Balance').text = float_to_str(
                abs(closing_balance))

            open_invoices = invoices.filtered(lambda x: x.partner_id.id == partner.id)
            if not open_invoices:
                continue
            open_invoices_element = SubElement(partner_element, 'Open' + invoice_node + 'Invoices')
            for invoice in open_invoices:
                open_invoice_element = SubElement(open_invoices_element, 'Open' + invoice_node + 'Invoice')
                invoice_number = invoice.number if partner_type == 'customer' else invoice.reference
                SubElement(open_invoice_element, 'InvoiceNo').text = invoice_number
                SubElement(open_invoice_element, 'InvoiceDate').text = invoice.date_invoice
                SubElement(open_invoice_element, 'GLPostingDate').text = invoice.date_invoice
                SubElement(open_invoice_element, 'TransactionID').text = str(invoice.move_id.id)
                SubElement(open_invoice_element, 'Amount').text = float_to_str(invoice.amount_total_company_signed)
                SubElement(open_invoice_element, 'CurrencyAmount').text = float_to_str(invoice.amount_total)
                SubElement(open_invoice_element, 'CurrencyCode1').text = invoice.currency_id.name
                SubElement(open_invoice_element, 'UnpaidAmount').text = float_to_str(invoice.residual_company_signed)
                SubElement(open_invoice_element, 'CurrencyUnpaidAmount').text = float_to_str(invoice.residual_signed)
                SubElement(open_invoice_element, 'CurrencyCode').text = invoice.currency_id.name
                debit_credit_indicator = 'D' if invoice.type in ['out_invoice', 'in_refund'] else 'K'
                SubElement(open_invoice_element, 'DebitCreditIndicator').text = debit_credit_indicator

    @api.model
    def get_tax_table(self, element):
        """
        Get taxes of all usage types present
        :param element: XML node element
        :return: None
        """
        tax_table = SubElement(element, 'TaxTable')
        self.get_taxes(tax_table, 'sale')
        self.get_taxes(tax_table, 'purchase')
        self.get_taxes(tax_table, 'none')
        self.get_profit_tax(tax_table)

    @api.model
    def get_taxes(self, element, type_tax_use):
        """
        Get taxes by usage type
        :param element: XML node element
        :param type_tax_use: purchase/sale/none
        :return: None
        """
        AccountTax = self.env['account.tax']
        taxes = AccountTax.search([('type_tax_use', '=', type_tax_use)])
        if not taxes:
            return
        tax_table_entry = SubElement(element, 'TaxTableEntry')
        SubElement(tax_table_entry, 'TaxType').text = 'PVM'
        type_tax_use_value = dict(AccountTax._fields['type_tax_use'].selection).get(type_tax_use)
        SubElement(tax_table_entry, 'Description').text = type_tax_use_value + ' PVM'

        tax_code_details = SubElement(tax_table_entry, 'TaxCodeDetails')
        for tax in taxes:
            tax_code_detail = SubElement(tax_code_details, 'TaxCodeDetail')
            SubElement(tax_code_detail, 'TaxCode').text = tax.code
            SubElement(tax_code_detail, 'Description').text = tax.name
            if tax.amount_type == 'fixed':
                flat_tax_rate = SubElement(tax_code_detail, 'FlatTaxRate')
                SubElement(flat_tax_rate, 'Amount').text = float_to_str(tax.amount)
            else:
                SubElement(tax_code_detail, 'TaxPercentage').text = float_to_str(tax.amount)
            SubElement(tax_code_detail, 'Country').text = 'LT'

    @api.multi
    def get_profit_tax(self, element):
        """
        Get profit tax details
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        if not self.saf_t_tax_id:
            return
        tax_table_entry = SubElement(element, 'TaxTableEntry')
        SubElement(tax_table_entry, 'TaxType').text = 'PM'
        SubElement(tax_table_entry, 'Description').text = 'Pelno mokestis'
        tax_code_details = SubElement(tax_table_entry, 'TaxCodeDetails')
        tax_code_detail = SubElement(tax_code_details, 'TaxCodeDetail')
        SubElement(tax_code_detail, 'TaxCode').text = self.saf_t_tax_id.code
        SubElement(tax_code_detail, 'Description').text = self.saf_t_tax_id.description
        SubElement(tax_code_detail, 'TaxPercentage').text = float_to_str(self.saf_t_tax_id.percentage)
        SubElement(tax_code_detail, 'Country').text = 'LT'

    @api.model
    def get_uom_table(self, element):
        """
        Get all units of measure
        :param element: XML node element
        :return: None
        """
        uom_table = SubElement(element, 'UOMTable')
        uoms = self.env['product.uom'].search([])
        for uom in uoms:
            uom_table_entry = SubElement(uom_table, 'UOMTableEntry')
            SubElement(uom_table_entry, 'UnitOfMeasure').text = uom.name
            SubElement(uom_table_entry, 'Description').text = uom.name

    @api.model
    def get_movement_type_table(self, element):
        """
        Get all stock movement types according to modules installed
        :param element: XML node element
        :return: None
        """
        Module = self.sudo().env['ir.module.module']
        robo_stock_is_installed = Module.search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to_upgrade'])])
        if not robo_stock_is_installed:
            return
        movement_types = SAFT_MOVEMENT_TYPE
        robo_mrp_is_installed = Module.search_count(
            [('name', '=', 'robo_mrp'), ('state', 'in', ['installed', 'to_upgrade'])])
        if not robo_mrp_is_installed:
            for movement_type in SAFT_PRODUCTION_MOVEMENTS:
                movement_types.pop(movement_type)
        movement_type_table = SubElement(element, 'MovementTypeTable')
        for movement_key, movement_value in movement_types.items():
            movement_type_table_entry = SubElement(movement_type_table, 'MovementTypeTableEntry')
            SubElement(movement_type_table_entry, 'MovementType').text = movement_key
            SubElement(movement_type_table_entry, 'Description').text = movement_value

    @api.model
    def get_products(self, element):
        """
        Get all products and services
        :param element: XML node element
        :return: None
        """
        products_element = SubElement(element, 'Products')
        product_domain = self.get_product_domain()
        products = self.env['product.product'].search(product_domain)
        for product in products:
            product_element = SubElement(products_element, 'Product')
            SubElement(product_element, 'ProductCode').text = product.default_code
            SubElement(product_element, 'GoodsServicesID').text = 'PR' if product.type in ['product', 'consu'] else 'PS'
            SubElement(product_element, 'Description').text = \
                product.with_context(lang='lt_LT').name[:DESCRIPTION_MAX_LENGTH]

            product_uom = product.uom_id.with_context(lang='lt_LT')
            SubElement(product_element, 'UOMBase').text = product.uom_id.name
            uoms_element = SubElement(product_element, 'UOMS')
            uom_element = SubElement(uoms_element, 'UOM')
            SubElement(uom_element, 'UOMStandard').text = product_uom.name
            SubElement(uom_element, 'UOMToUOMBaseConversionFactor').text = float_to_str(product_uom.factor)

            if product.taxes_id or product.supplier_taxes_id:
                taxes_element = SubElement(product_element, 'Taxes')
                for tax in (product.taxes_id, product.supplier_taxes_id):
                    if not tax:
                        continue
                    tax_element = SubElement(taxes_element, 'Tax')
                    SubElement(tax_element, 'TaxType').text = 'PVM'
                    SubElement(tax_element, 'TaxCode').text = tax.code

    @api.multi
    def get_physical_stock(self, element):
        """
        Get product stock for each internal stock location at starting/ending period dates
        :param element: XMl node element
        :return: None
        """
        robo_stock_is_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to_upgrade'])])
        if not robo_stock_is_installed:
            return
        self.ensure_one()
        physical_stock = SubElement(element, 'PhysicalStock')
        product_domain = self.get_product_domain()
        products = self.env['product.product'].search(product_domain)
        locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

        stock_from_date = (date_from_dt + relativedelta(days=-1, hour=21)).\
            strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        stock_to_date = (date_to_dt + relativedelta(hour=21)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        stock_from_data = self.get_stock_data(products._ids, locations._ids, stock_from_date)
        stock_to_data = self.get_stock_data(products._ids, locations._ids, stock_to_date)
        for product in products:
            for location in locations:
                product_stock_from = [x for x in stock_from_data if x['product_id'][0] == product.id and
                                      x['location_id'][0] == location.id]
                product_stock_to = [x for x in stock_to_data if x['product_id'][0] == product.id and
                                    x['location_id'][0] == location.id]
                if not product_stock_from or not product_stock_to:
                    continue
                opening_qty = round(sum(x['quantity'] for x in product_stock_from), 2)
                opening_value = round(sum(x['total_value'] for x in product_stock_from), 2)
                closing_qty = round(sum(x['quantity'] for x in product_stock_to), 2)
                closing_value = round(sum(x['total_value'] for x in product_stock_to), 2)

                physical_stock_entry = SubElement(physical_stock, 'PhysicalStockEntry')
                product_purchase_uom = product.uom_po_id.with_context(lang='lt_LT')
                SubElement(physical_stock_entry, 'WarehouseID').text = location.warehouse_id.code
                SubElement(physical_stock_entry, 'ProductCode').text = product.default_code
                SubElement(physical_stock_entry, 'UOMPhysicalStock').text = product_purchase_uom.name
                SubElement(physical_stock_entry, 'UOMToUOMBaseConversionFactor').text = float_to_str(
                    product_purchase_uom.factor)

                SubElement(physical_stock_entry, 'OpeningStockQuantity').text = float_to_str(opening_qty)
                SubElement(physical_stock_entry, 'OpeningStockValue').text = float_to_str(opening_value)
                SubElement(physical_stock_entry, 'ClosingStockQuantity').text = float_to_str(closing_qty)
                SubElement(physical_stock_entry, 'ClosingStockValue').text = float_to_str(closing_value)

    @api.multi
    def get_assets(self, element):
        """
        Get all assets accounted in the selected period
        :param element: XML node element
        :return: None
        """
        self.ensure_one()
        assets = self.get_related_assets()
        if not assets:
            return
        self.check_partner_type(assets.mapped('invoice_id.partner_id'), 'supplier')
        DepreciationLine = self.env['account.asset.depreciation.line']
        assets_element = SubElement(element, 'Assets')
        for asset in assets:
            asset_account_code = asset.account_asset_id.code or asset.category_id.account_asset_id.code
            asset_element = SubElement(assets_element, 'Asset')
            SubElement(asset_element, 'AssetID').text = asset.code
            SubElement(asset_element, 'AccountID').text = asset_account_code
            SubElement(asset_element, 'Description').text = asset.name[:DESCRIPTION_MAX_LENGTH]

            supplier = asset.invoice_id.partner_id or False
            if supplier:
                suppliers_element = SubElement(asset_element, 'Suppliers')
                supplier_element = SubElement(suppliers_element, 'Supplier')
                SubElement(supplier_element, 'SupplierName').text = supplier.name
                SubElement(supplier_element, 'SupplierID').text = str(supplier.id)
                postal_address = SubElement(supplier_element, 'PostalAddress')
                self.get_address_structure(postal_address, supplier)

            if asset.pirkimo_data:
                SubElement(asset_element, 'DateOfAcquisition').text = asset.pirkimo_data
            SubElement(asset_element, 'StartUpDate').text = asset.date

            valuations_element = SubElement(asset_element, 'Valuations')
            valuation_element = SubElement(valuations_element, 'Valuation')
            SubElement(valuation_element, 'AccountID').text = asset_account_code
            SubElement(valuation_element, 'AcquisitionAndProductionCostsBegin').text = float_to_str(asset.value)
            SubElement(valuation_element, 'AcquisitionAndProductionCostsEnd').text = float_to_str(asset.value)
            SubElement(valuation_element, 'AssetLifeMonth').text = str(asset.method_number)

            book_value_begin_line = DepreciationLine.search([('asset_id', '=', asset.id),
                                                             ('depreciation_date', '>=', self.date_from)],
                                                            order='depreciation_date', limit=1)
            book_value_begin = book_value_begin_line.total_amount_to_be_depreciated if book_value_begin_line \
                else asset.current_value
            book_value_end_line = DepreciationLine.search([('asset_id', '=', asset.id),
                                                           ('depreciation_date', '<=', self.date_to)],
                                                          order='depreciation_date desc', limit=1)
            book_value_end = book_value_end_line.total_amount_to_be_depreciated if book_value_end_line \
                else asset.current_value

            SubElement(valuation_element, 'BookValueBegin').text = float_to_str(book_value_begin)
            SubElement(valuation_element, 'DepreciationForPeriod').text = float_to_str(
                book_value_begin - book_value_end)
            SubElement(valuation_element, 'BookValueEnd').text = float_to_str(book_value_end)
            SubElement(asset_element, 'DepreciationDate').text = asset.date_first_depreciation

    @api.model
    def get_owners(self, element):
        """
        Get shareholders of the company
        :param element: XML node element
        :return: None
        """
        shareholders = self.env['res.company.shareholder'].search([])
        if not shareholders:
            return
        owners_element = SubElement(element, 'Owners')
        shareholder_account_code = '3011'
        shareholder_account = self.env['account.account'].search([('code', '=', shareholder_account_code)], limit=1)
        if not shareholder_account:
            raise exceptions.ValidationError(_('Nerasta didžiosios knygos sąskaita %s.') % shareholder_account_code)

        for shareholder in shareholders:
            owner_element = SubElement(owners_element, 'Owner')
            SubElement(owner_element, 'OwnerID').text = shareholder.shareholder_personcode
            SubElement(owner_element, 'OwnerName').text = shareholder.shareholder_name
            SubElement(owner_element, 'AccountID').text = shareholder_account.code
            SubElement(owner_element, 'SharesQuantity').text = float_to_str(shareholder.shareholder_shares)

    """ GeneralLedgerEntries node """

    @api.multi
    def get_journals(self):
        """
        Get journals, their moves and move lines
        :return: Sub-element of journals information, total number of entries, debit amount, credit amount
        """
        self.ensure_one()
        AccountMove = self.env['account.move']
        journals = self.env['account.journal'].with_context(active_test=False).search([])
        journals_element = Element('Journals')
        company = self.env.user.sudo().company_id
        date = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        fiscal_year = company.compute_fiscalyear_dates(date=date)
        fiscal_year_start_dt = fiscal_year['date_from']
        number_of_entries, total_debit, total_credit = 0, 0.0, 0.0
        # A partner created specifically for a fill-in of move lines with no partner
        undefined_partner = self.env['res.partner'].search([('name', '=', UNDEFINED_PARTNER_NAME)], limit=1)
        for journal in journals:
            moves = AccountMove.search([('journal_id', '=', journal.id),
                                        ('date', '>=', self.date_from), ('date', '<=', self.date_to),
                                        ('state', '=', 'posted')])
            if not moves:
                continue
            journal_element = SubElement(journals_element, 'Journal')
            SubElement(journal_element, 'JournalID').text = journal.code
            SubElement(journal_element, 'Description').text = journal.name
            SubElement(journal_element, 'Type').text = journal.type
            transactions = SubElement(journal_element, 'Transactions')
            partners_to_check = moves.mapped('line_ids.partner_id').filtered(lambda x: not x.customer)
            # Check the remaining partners to have a supplier flag set
            self.check_partner_type(partners_to_check, 'supplier')
            for move in moves:
                move_lines = move.line_ids
                if not move_lines:
                    continue
                partners = move_lines.mapped('partner_id')
                # Set the partner from move lines, if possible. Otherwise, use an undefined partner record
                move_partner = partners[0] if len(move_lines) == 2 and len(set(partners.ids)) == 1 \
                    else undefined_partner
                move_partner_type = 'Customer' if move_partner.customer else 'Supplier'
                number_of_entries += 1
                transaction = SubElement(transactions, 'Transaction')
                SubElement(transaction, 'TransactionID').text = str(move.id)

                move_date_dt = datetime.strptime(move.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                # Get a number of months since the start of the fiscal year
                period = (move_date_dt.year - fiscal_year_start_dt.year) * 12 + \
                         (move_date_dt.month - fiscal_year_start_dt.month) + 1
                SubElement(transaction, 'Period').text = str(period)
                SubElement(transaction, 'PeriodYear').text = str(fiscal_year_start_dt.year)
                SubElement(transaction, 'TransactionDate').text = move.date
                SubElement(transaction, 'Description').text = move.ref
                SubElement(transaction, 'SystemEntryDate').text = datetime.\
                    strptime(move.create_date, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(DATETIME_FORMAT)
                SubElement(transaction, 'GLPostingDate').text = move.date
                SubElement(transaction, move_partner_type + 'ID').text = str(move_partner.id)
                lines = SubElement(transaction, 'Lines')
                for line in move_lines:
                    total_debit += line.debit
                    total_credit += line.credit
                    line_partner = line.partner_id or move_partner
                    line_partner_type = 'Customer' if line_partner.customer else 'Supplier'
                    line_element = SubElement(lines, 'Line')

                    SubElement(line_element, 'RecordID').text = str(line.id)
                    SubElement(line_element, 'AccountID').text = line.account_id.code
                    SubElement(line_element, line_partner_type + 'ID').text = str(line_partner.id)
                    SubElement(line_element, 'Description').text = line.name
                    amount_node = 'Debit' if not tools.float_is_zero(line.debit, precision_digits=2) else 'Credit'
                    amount_element = SubElement(line_element, amount_node + 'Amount')

                    SubElement(amount_element, 'Amount').text = float_to_str(abs(line.balance))
                    if line.currency_id and not tools.float_is_zero(line.amount_currency,
                                                                    precision_rounding=line.currency_id.rounding):
                        SubElement(amount_element, 'CurrencyCode').text = line.currency_id.name
                        SubElement(amount_element, 'CurrencyAmount').text = float_to_str(abs(line.amount_currency))
        return journals_element, number_of_entries, total_debit, total_credit

    """ SourceDocuments node """

    @api.multi
    def get_movement_of_goods(self):
        """
        Get all stock moves
        :return: List of movement sub-elements, Number of total stock moves (number_of_entries),
        total quantity received (total_qty_received), total quantity sent (total_qty_issued)
        """

        no_code_products = self.env['stock.move'].search([('date', '<=', self.date_to), ('date', '>=', self.date_from),
                                                          ('product_id.default_code', '=', False)]).mapped('product_id')
        if no_code_products:
            raise exceptions.ValidationError(_('Šie produktai neturi kodo:\n %s') %
                                             '\n'.join(no_code_products.mapped('name')))
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        movement_elements = []
        number_of_entries, total_qty_received, total_qty_issued = 0, 0.0, 0.0
        pickings = self.env['stock.picking'].search([('state', '=', 'done'), ('date', '<=', self.date_to),
                                                     ('date', '>=', self.date_from), ('cancel_state', '!=', 'error')])
        inventories = self.env['stock.inventory'].search([('state', '=', 'done'),
                                                          ('accounting_date', '<=', self.date_to),
                                                          ('accounting_date', '>=', self.date_from)])
        for picking in pickings:
            moves = picking.move_lines.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            accounting_lines = MoveLine.search([('move_id.state', '=', 'posted'), ('ref', '=', picking.name)])
            if not accounting_lines:
                continue
            number_of_entries += 1
            movement_type = self.get_movement_type(picking.picking_type_id)
            stock_movement = Element('StockMovement')
            SubElement(stock_movement, 'MovementReference').text = picking.name
            SubElement(stock_movement, 'MovementDate').text = \
                datetime.strptime(picking.date, tools.DEFAULT_SERVER_DATETIME_FORMAT). \
                    strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            # There is no 'NG' movement type but it's needed to correctly collect received/issued stock
            SubElement(stock_movement, 'MovementType').text = movement_type if movement_type != 'NG' else 'KT'
            lines_element = SubElement(stock_movement, 'Lines')
            line_elements, received, issued = self.get_movement_lines(moves, accounting_lines, movement_type,
                                                                      picking.partner_id)
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)
            movement_elements.append(stock_movement)

        for inventory in inventories:
            moves = inventory.move_ids.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            accounting_lines = MoveLine.search([('move_id.state', '=', 'posted'), '|',
                                                ('inventory_id', '=', inventory.id), ('ref', '=', inventory.number)])
            if not accounting_lines:
                continue
            number_of_entries += 1
            movement_type = 'NG' if inventory.surplus else 'N'
            stock_movement = Element('StockMovement')
            SubElement(stock_movement, 'MovementReference').text = inventory.number
            SubElement(stock_movement, 'MovementDate').text = inventory.accounting_date
            # There is no 'NG' movement type but it's needed to correctly collect received/issued stock
            SubElement(stock_movement, 'MovementType').text = movement_type if movement_type != 'NG' else 'KT'
            lines_element = SubElement(stock_movement, 'Lines')
            line_elements, received, issued = self.get_movement_lines(moves, accounting_lines, movement_type)
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)
            movement_elements.append(stock_movement)

        collect_mrp = self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_mrp'), ('state', 'in', ['installed', 'to_upgrade'])])

        if not collect_mrp:
            return movement_elements, number_of_entries, total_qty_received, total_qty_issued

        productions = self.env['mrp.production'].search([('state', '=', 'done'),
                                                         ('accounting_date', '<=', self.date_to),
                                                         ('accounting_date', '>=', self.date_from)])
        unbuilds = self.env['mrp.unbuild'].search([('state', '=', 'done'), ('build_date', '<=', self.date_to),
                                                   ('build_date', '>=', self.date_from)])

        for production in productions:
            moves = production.move_finished_ids.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            accounting_lines = MoveLine.search([('move_id.state', '=', 'posted'), ('name', '=', production.name)])
            if not accounting_lines:
                continue
            number_of_entries += 1
            stock_movement = Element('StockMovement')

            SubElement(stock_movement, 'MovementReference').text = production.name
            SubElement(stock_movement, 'MovementDate').text = \
                datetime.strptime(production.accounting_date, tools.DEFAULT_SERVER_DATETIME_FORMAT). \
                    strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            SubElement(stock_movement, 'MovementType').text = 'PP'
            lines_element = SubElement(stock_movement, 'Lines')
            line_elements, received, issued = self.get_movement_lines(moves, accounting_lines, 'PP',
                                                                      debit_credit_indicator='D')
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)

            moves = production.move_raw_ids.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            line_elements, received, issued = self.get_movement_lines(moves, accounting_lines, 'PP',
                                                                      debit_credit_indicator='K')
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)
            movement_elements.append(stock_movement)

        for unbuild in unbuilds:
            moves = unbuild.consume_line_ids.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            accounting_lines = MoveLine.search([('move_id.state', '=', 'posted'), ('name', '=', unbuild.name)])
            if not accounting_lines:
                continue
            number_of_entries += 1
            stock_movement = Element('StockMovement')

            SubElement(stock_movement, 'MovementReference').text = unbuild.name
            SubElement(stock_movement, 'MovementDate').text = \
                datetime.strptime(unbuild.build_date, tools.DEFAULT_SERVER_DATETIME_FORMAT). \
                    strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            SubElement(stock_movement, 'MovementType').text = 'PP'

            lines_element = SubElement(stock_movement, 'Lines')
            line_elements, received, issued = self.get_movement_lines(lines_element, moves, accounting_lines, 'PP',
                                                                      debit_credit_indicator='K')
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)

            moves = unbuild.produce_line_ids.filtered(lambda x: x.state == 'done')
            if not moves:
                continue
            line_elements, received, issued = self.get_movement_lines(lines_element, moves, accounting_lines, 'PP',
                                                                      debit_credit_indicator='D')
            total_qty_received += received
            total_qty_issued += issued
            lines_element.extend(line_elements)
            movement_elements.append(stock_movement)

        return movement_elements, number_of_entries, total_qty_received, total_qty_issued

    @api.multi
    def get_invoices(self, invoice_type):
        """
        Get invoices and their total amounts
        :return: List of sub-element of invoices information, total number of entries, debit amount, credit amount
        :return: A list of invoice elements, total number of invoices, total invoice debit amount,
        total invoice credit amount
        """
        self.ensure_one()
        invoice_elements = []
        invoice_types = ['out_invoice', 'out_refund'] if invoice_type == 'out' else ['in_invoice', 'in_refund']
        partner_type = 'customer' if invoice_type == 'out' else 'supplier'
        invoices = self.env['account.invoice'].search([('type', 'in', invoice_types),
                                                       ('date_invoice', '<=', self.date_to),
                                                       ('date_invoice', '>=', self.date_from),
                                                       ('state', 'in', ['open', 'paid'])])
        number_of_entries, total_debit, total_credit = 0, 0.0, 0.0
        partners_to_check = invoices.mapped('partner_id')
        self.check_partner_type(partners_to_check, partner_type)
        for invoice in invoices:
            number_of_entries += 1
            total_debit += abs(invoice.amount_total_company_signed) if invoice.type in ['out_invoice', 'in_refund'] \
                else 0.0
            total_credit += abs(invoice.amount_total_company_signed) if invoice.type in ['out_refund', 'in_invoice'] \
                else 0.0
            invoice_element = Element('Invoice')
            self.get_invoice_structure(invoice_element, invoice)
            invoice_elements.append(invoice_element)
        return invoice_elements, number_of_entries, total_debit, total_credit

    @api.model
    def get_movement_lines(self, moves, accounting_lines, move_type, partner=None, debit_credit_indicator=None):
        """
        Get all stock-related document move lines
        :param moves: Stock moves
        :param accounting_lines: Corresponding move lines
        :param move_type: SAF-T move type
        :param partner: Partner related to the movement
        :param debit_credit_indicator: Indicator if amount is debit or credit
        :return: List of line elements, total quantity received, total quantity issued
        """
        # A partner created specifically for a fill-in of move lines with no partner
        undefined_partner = self.env['res.partner'].search([('name', '=', UNDEFINED_PARTNER_NAME)], limit=1)
        supplier = partner if partner and move_type in ['PIR', 'PRG'] else undefined_partner
        customer = partner if partner and move_type in ['PARD', 'PG'] else undefined_partner
        line_number = 0
        total_qty_received, total_qty_issued = 0.0, 0.0
        line_elements = []
        if not debit_credit_indicator:
            debit_credit_indicator = 'K' if move_type in ['PARD', 'PGR', 'N'] else 'D'
        for move in moves:
            move_line = self.get_corresponding_move_line(move, accounting_lines, debit_credit_indicator)
            if not move_line:
                continue
            line_element = Element('Line')
            product_uom = move.product_uom.with_context(lang='lt_LT')
            line_number += 1
            if move_type in ['PIR', 'PG', 'NG']:  # Purchase/Sale return/Surplus
                total_qty_received += move.product_qty
            if move_type in ['PARD', 'PGR', 'N']:  # Sale/Purchase return/Write-off
                total_qty_issued += move.product_qty
            SubElement(line_element, 'LineNumber').text = str(line_number)
            SubElement(line_element, 'AccountID').text = move_line.account_id.code
            SubElement(line_element, 'TransactionID').text = str(move_line.move_id.id)
            SubElement(line_element, 'CustomerID').text = str(customer.id)
            SubElement(line_element, 'SupplierID').text = str(supplier.id)
            SubElement(line_element, 'ProductCode').text = move.product_id.default_code or str()
            SubElement(line_element, 'Quantity').text = float_to_str(move.product_qty)
            SubElement(line_element, 'UnitOfMeasure').text = product_uom.name
            SubElement(line_element, 'UOMToUOMPhysicalStockConversionFactor').text = float_to_str(product_uom.factor)
            SubElement(line_element, 'BookValue').text = float_to_str(abs(move_line.balance))
            SubElement(line_element, 'MovementSubType').text = move_type
            SubElement(line_element, 'DebitCreditIndicator').text = debit_credit_indicator
            line_elements.append(line_element)

        return line_elements, total_qty_received, total_qty_issued

    @api.multi
    def get_asset_transactions(self):
        """
        Get all asset transactions and their count
        :return: List of transaction sub-elements, number of total entries (number_of_entries)
        """
        self.ensure_one()
        assets = self.get_related_assets()
        if not assets:
            return
        asset_transactions = []
        number_of_entries = 0
        for asset in assets:
            posted_depreciation_lines = asset.depreciation_line_ids.filtered(lambda x: x.move_check and self.date_from
                                                                                       <= x.depreciation_date <=
                                                                                       self.date_to)
            # Acquisition of asset
            invoice = asset.invoice_id
            if invoice and self.date_from <= invoice.date_invoice <= self.date_to:
                transaction = self.get_asset_transaction(asset, 'I', invoice.move_id,
                                                         abs(invoice.amount_total_company_signed), 'D',
                                                         invoice.partner_id)
                asset_transactions.append(transaction)
                number_of_entries += 1

            for depreciation in posted_depreciation_lines:
                move = depreciation.move_ids[0] if depreciation.move_ids else False
                if not move:
                    continue
                amount = depreciation.amount + depreciation.revaluation_depreciation
                transaction = self.get_asset_transaction(asset, 'NUS', move, amount, 'K')
                number_of_entries += 1
                asset_transactions.append(transaction)

            # Changes
            changes = asset.change_line_ids.filtered(lambda x: self.date_from <= x.date <= self.date_to)
            for change in changes:
                move = asset.move_ids.filtered(lambda x: x.date == change.date and not tools.float_compare(
                    abs(x.amount), abs(change.change_amount), precision_digits=2))
                if not move:
                    continue
                transaction = self.get_asset_transaction(asset, 'KT', move[0], abs(change.change_amount), 'D')
                number_of_entries += 1
                asset_transactions.append(transaction)

            # Revaluations
            revaluations = asset.revaluation_history_ids.filtered(lambda x: self.date_from <= x.date <= self.date_to)
            for revaluation in revaluations:
                move = asset.move_ids.filtered(lambda x:
                                               x.date == revaluation.date and not tools.float_compare(
                                                   abs(x.amount),
                                                   abs(revaluation.value_difference), precision_digits=2))
                if not move:
                    continue
                debit_credit_indicator = 'D' \
                    if tools.float_compare(revaluation.value_difference, 0.0, precision_digits=2) == 1 else 'K'
                transaction = self.get_asset_transaction(asset, 'VJ', move[0], abs(revaluation.value_difference),
                                                         debit_credit_indicator)
                number_of_entries += 1
                asset_transactions.append(transaction)

            # Sales
            sales = asset.sale_line_ids.filtered(lambda x: self.date_from <= x.invoice_id.date_invoice <= self.date_to
                                                           and x.invoice_id.state in ['open', 'paid'])
            for sale in sales:
                invoice = sale.invoice_id
                transaction = self.get_asset_transaction(asset, 'KT', invoice.move_id, abs(invoice.move_id.amount), 'K')
                number_of_entries += 1
                asset_transactions.append(transaction)

            # Write-off
            if asset.writeoff_move_id:
                transaction = self.get_asset_transaction(asset, 'NUR', asset.writeoff_move_id,
                                                         abs(asset.writeoff_move_id.amount), 'K')
                number_of_entries += 1
                asset_transactions.append(transaction)

        return asset_transactions, number_of_entries

    @api.model
    def get_asset_transaction(self, asset, transaction_type, move, amount, debit_credit_indicator, supplier=None):
        """
        Get XML node structure of an asset transaction
        :param asset: Asset record
        :param transaction_type: SAF-T asset transaction type
        :param move: Move related to asset transaction
        :param amount: Transaction amount
        :param debit_credit_indicator: Indicator whether it credits or debits asset value
        :param supplier: Supplier related to the transaction
        :return: Transaction XML node element
        """
        element = Element('AssetTransaction')
        date_dt = datetime.strptime(move.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        book_value = asset.with_context(date=date_from).value_at_date

        SubElement(element, 'AssetTransactionID').text = str(move.id)
        SubElement(element, 'AssetID').text = asset.code
        SubElement(element, 'AssetTransactionType').text = transaction_type
        SubElement(element, 'AssetTransactionDate').text = move.date
        if supplier:
            supplier_element = SubElement(element, 'Supplier')
            SubElement(supplier_element, 'SupplierName').text = supplier.name
            SubElement(supplier_element, 'SupplierID').text = str(supplier.id)
            postal_address = SubElement(supplier_element, 'PostalAddress')
            self.get_address_structure(postal_address, supplier)

        SubElement(element, 'TransactionID').text = str(move.id)
        trans_valuations = SubElement(element, 'AssetTransactionValuations')
        trans_valuation = SubElement(trans_valuations, 'AssetTransactionValuation')
        SubElement(trans_valuation, 'AcquisitionAndProductionCostsOnTransaction').text = float_to_str(asset.value)
        SubElement(trans_valuation, 'BookValueOnTransaction').text = float_to_str(book_value)
        SubElement(trans_valuation, 'AssetTransactionAmount').text = \
            float_to_str(amount)
        SubElement(trans_valuation, 'DebitCreditIndicator').text = debit_credit_indicator

        return element

    @api.multi
    def get_payments(self):
        """
        Get all inbound and outbound payments
        :return: List of payment sub-elements, number of total entries (number_of_entries),
        total amount issued (total_debit), total amount received (total_credit)
        """
        self.ensure_one()
        payments = self.env['account.payment'].search([('payment_date', '>=', self.date_from),
                                                       ('payment_date', '<=', self.date_to),
                                                       ('payment_type', 'in', ['outbound', 'inbound', 'advance']),
                                                       ('move_line_ids', '!=', False),
                                                       ('state', 'not in', ['draft', 'canceled'])])
        payment_elements = []
        number_of_entries, total_debit, total_credit = 0, 0.0, 0.0
        undefined_partner = self.env['res.partner'].search([('name', '=', UNDEFINED_PARTNER_NAME)], limit=1)
        for payment in payments:
            field_not_zero = 'credit' if payment.payment_type == 'outbound' else 'debit'
            payment_move_lines = payment.move_line_ids.filtered(lambda x:
                                                                x.move_id.state == 'posted' and
                                                                not tools.float_is_zero(x[field_not_zero],
                                                                                        precision_digits=2))
            if not payment_move_lines:
                continue
            number_of_entries += 1
            total_debit += 0.0 if tools.float_compare(payment.amount, 0.0, precision_digits=2) <= 0 else payment.amount
            total_credit += 0.0 if tools.float_compare(payment.amount, 0.0, precision_digits=2) >= 0 else payment.amount
            payment_element = Element('Payment')
            SubElement(payment_element, 'PaymentRefNo').text = payment.payment_reference
            transactions = payment_move_lines.mapped('move_id')
            SubElement(payment_element, 'TransactionID').text = str(transactions[0].id)
            SubElement(payment_element, 'TransactionDate').text = payment.payment_date
            SubElement(payment_element, 'Description').text = payment.communication[:DESCRIPTION_MAX_LENGTH]
            lines_element = SubElement(payment_element, 'Lines')
            line_number = 0
            for line in payment_move_lines:
                line_number += 1
                partner = line.partner_id
                customer = partner if partner and partner.customer else undefined_partner
                supplier = partner if partner and partner.supplier and not partner.customer else undefined_partner
                line_element = SubElement(lines_element, 'Line')
                SubElement(line_element, 'LineNumber').text = str(line_number)
                SubElement(line_element, 'AccountID').text = line.account_id.code
                SubElement(line_element, 'CustomerID').text = str(customer.id)
                SubElement(line_element, 'SupplierID').text = str(supplier.id)
                SubElement(line_element, 'Description').text = line.name
                debit_credit_indicator = 'D' if tools.float_compare(line.balance, 0.0, precision_digits=2) >= 0 else 'K'
                SubElement(line_element, 'DebitCreditIndicator').text = debit_credit_indicator

                payment_line_amount = SubElement(line_element, 'PaymentLineAmount')
                SubElement(payment_line_amount, 'Amount').text = float_to_str(abs(line.balance))
                if line.currency_id and not tools.float_is_zero(line.amount_currency,
                                                                precision_rounding=line.currency_id.rounding):
                    SubElement(payment_line_amount, 'CurrencyCode').text = line.currency_id.name
                    SubElement(payment_line_amount, 'CurrencyAmount').text = float_to_str(abs(line.amount_currency))

            SubElement(payment_element, 'GrossTotal').text = float_to_str(payment.amount)
            payment_elements.append(payment_element)

        return payment_elements, number_of_entries, total_debit, total_credit

    """ SourceDocuments node - totals """

    @api.model
    def get_invoices_total(self, element, invoice_type):
        """
        Get invoices and their total count according to invoice type - sums node
        :param element: XML node element
        :param invoice_type: in/out
        :return: None
        """
        invoice_node = 'Sales' if invoice_type == 'out' else 'Purchase'
        invoices, number_of_entries, total_debit, total_credit = self.get_invoices(invoice_type)
        if not number_of_entries:
            return
        sales_invoices = SubElement(element, invoice_node + 'Invoices')
        SubElement(sales_invoices, 'NumberOfEntries').text = str(number_of_entries)
        SubElement(sales_invoices, 'TotalDebit').text = float_to_str(total_debit)
        SubElement(sales_invoices, 'TotalCredit').text = float_to_str(total_credit)
        for invoice in invoices:
            sales_invoices.append(invoice)

    @api.model
    def get_payments_total(self, element):
        """
        Get payments and their total amounts - sums node
        :param element: XML node element
        :return: None
        """
        payments, number_of_entries, total_debit, total_credit = self.get_payments()
        if not number_of_entries:
            return
        payments_element = SubElement(element, 'Payments')
        SubElement(payments_element, 'NumberOfEntries').text = str(number_of_entries)
        SubElement(payments_element, 'TotalDebit').text = float_to_str(total_debit)
        SubElement(payments_element, 'TotalCredit').text = float_to_str(total_credit)
        for payment in payments:
            payments_element.append(payment)

    @api.model
    def get_movement_of_goods_total(self, element):
        """
        Get all stock moves and their totals - sums node
        :param element: XML node element
        :return: None
        """
        robo_stock_is_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to_upgrade'])])
        if not robo_stock_is_installed:
            return
        movements, number_of_lines, total_qty_received, total_qty_issued = self.get_movement_of_goods()
        if not number_of_lines:
            return
        movement_of_goods = SubElement(element, 'MovementOfGoods')
        SubElement(movement_of_goods, 'NumberOfMovementLines').text = str(number_of_lines)
        SubElement(movement_of_goods, 'TotalQuantityReceived').text = float_to_str(total_qty_received)
        SubElement(movement_of_goods, 'TotalQuantityIssued').text = float_to_str(total_qty_issued)
        for movement in movements:
            movement_of_goods.append(movement)

    @api.model
    def get_asset_transactions_total(self, element):
        """
        Get asset transactions and their total count - sums node
        :param element: XML node element
        :return: None
        """
        transactions, number_of_lines = self.get_asset_transactions()
        if not number_of_lines:
            return
        asset_transactions_element = SubElement(element, 'AssetTransactions')
        SubElement(asset_transactions_element, 'NumberOfAssetTransactions').text = str(number_of_lines)
        for transaction in transactions:
            asset_transactions_element.append(transaction)

    """Structure elements"""

    @api.model
    def get_bank_account_structure(self, element, bank_account_number):
        """
        BankAccountStructure element
        """
        SubElement(element, 'IBANNumber').text = bank_account_number

    @api.model
    def get_person_name_structure(self, element, partner):
        """
        PersonNameStructure element
        """
        names = partner.name.split()
        first_name = " ".join(names[0:-1])
        last_name = names[-1] if len(names) > 1 else ''

        SubElement(element, 'FirstName').text = first_name
        SubElement(element, 'LastName').text = last_name

    @api.model
    def get_address_structure(self, element, partner):
        """
        AddressStructure element
        """
        SubElement(element, 'StreetName').text = partner.street or str()
        SubElement(element, 'Number').text = partner.street2 or str()
        SubElement(element, 'City').text = (partner.city or str())[:35]
        SubElement(element, 'PostalCode').text = partner.zip or str()
        SubElement(element, 'Country').text = partner.country_id.code if partner.country_id else str()
        SubElement(element, 'AddressType').text = 'RA'

    @api.model
    def get_invoice_structure(self, element, invoice):
        """
        InvoiceStructure element
        """
        company = self.env.user.sudo().company_id
        company_currency = company.currency_id
        price_unit_digits = self.env['decimal.precision'].precision_get('Product Price')
        is_supplier_invoice = invoice.type in ['in_invoice', 'in_refund']
        debit_credit_indicator = 'D' if invoice.type in ['out_invoice', 'in_refund'] else 'K'
        invoice_number = invoice.reference if is_supplier_invoice else invoice.number
        SubElement(element, 'InvoiceNo').text = invoice_number

        partner_node = 'Supplier' if is_supplier_invoice else 'Customer'
        partner_element = SubElement(element, partner_node + 'Info')
        partner = invoice.partner_id
        SubElement(partner_element, partner_node + 'ID').text = str(partner.id)
        SubElement(partner_element, 'TaxRegistrationNumber').text = partner.vat or partner.kodas or str()
        tax_type = 'PVM' if partner.vat or partner.partner_code_type == 'PVMmk' else str()
        tax_type = 'MMR' if not tax_type and partner.partner_code_type == 'mmak' else 'KT'
        SubElement(partner_element, 'TaxType').text = tax_type
        SubElement(partner_element, 'Country').text = partner.country_id.code

        SubElement(element, 'AccountID').text = invoice.account_id.code
        SubElement(element, 'InvoiceDate').text = invoice.date_invoice
        invoice_type = 'AN' if invoice.state == 'cancel' else SAFT_INVOICE_TYPE_MAPPER.get(invoice.type)
        SubElement(element, 'InvoiceType').text = invoice_type
        SubElement(element, 'TransactionID').text = str(invoice.move_id.id)
        line_number = 0
        currency = invoice.currency_id
        for line in invoice.invoice_line_ids:
            line_number += 1
            line_element = SubElement(element, 'Line')
            SubElement(line_element, 'LineNumber').text = str(line_number)
            SubElement(line_element, 'AccountID').text = line.account_id.code

            # Corresponding to the product domain used in MasterFiles
            if line.product_id.default_code and not line.product_id.robo_product and not line.product_id.landed_cost_ok:
                SubElement(line_element, 'ProductCode').text = line.product_id.default_code
            SubElement(line_element, 'Quantity').text = float_to_str(line.quantity)
            SubElement(line_element, 'InvoiceUOM').text = line.uom_id.name
            price_unit = line.price_unit_tax_excluded_company * (1 - (line.discount or 0.0) / 100.0)
            SubElement(line_element, 'UnitPrice').text = float_to_str(price_unit, price_unit_digits)
            SubElement(line_element, 'TaxPointDate').text = invoice.date_invoice
            SubElement(line_element, 'Description').text = line.name[:DESCRIPTION_MAX_LENGTH]

            total_line_amount = tools.float_round(price_unit * line.quantity, precision_rounding=currency.rounding)
            invoice_line_amount = SubElement(line_element, 'InvoiceLineAmount')
            SubElement(invoice_line_amount, 'Amount').text = float_to_str(abs(total_line_amount))
            if currency.id != company.currency_id.id:
                SubElement(invoice_line_amount, 'CurrencyCode').text = invoice.currency_id.name
                SubElement(invoice_line_amount, 'CurrencyAmount').text = float_to_str(abs(line.total_with_tax_amount))
            SubElement(line_element, 'DebitCreditIndicator').text = debit_credit_indicator

            line_tax_amount = line.total_with_tax_amount_company - line.price_subtotal_signed
            line_tax = line.invoice_line_tax_ids[0] if line.invoice_line_tax_ids else False
            if not tools.float_is_zero(line_tax_amount, precision_digits=2) and line_tax:
                line_tax_information = SubElement(line_element, 'TaxInformation')
                SubElement(line_tax_information, 'TaxType').text = 'PVM'
                SubElement(line_tax_information, 'TaxCode').text = line_tax.code
                line_tax_amount_element = SubElement(line_tax_information, 'TaxAmount')
                line_tax_amount_company = line_tax_amount if currency.id == company_currency.id else \
                    currency.with_context(date=invoice.date_invoice).compute(line_tax_amount, company_currency)
                SubElement(line_tax_amount_element, 'Amount').text = float_to_str(abs(line_tax_amount_company))
                if currency.id != company_currency.id:
                    SubElement(line_tax_amount_element, 'CurrencyCode').text = currency.name
                    SubElement(line_tax_amount_element, 'CurrencyAmount').text = float_to_str(abs(line_tax_amount))

        document_totals = SubElement(element, 'DocumentTotals')
        # No negative tax amounts should be provided
        total_tax_amount = sum(x.amount for x in invoice.tax_line_ids)
        if not tools.float_is_zero(total_tax_amount, precision_digits=2):
            for tax in invoice.tax_line_ids:
                tax_information_totals = SubElement(document_totals, 'TaxInformationTotals')
                SubElement(tax_information_totals, 'TaxType').text = 'PVM'
                SubElement(tax_information_totals, 'TaxCode').text = tax.tax_id.code
                tax_amount_element = SubElement(tax_information_totals, 'TaxAmount')
                tax_currency = tax.currency_id
                tax_amount_company = tax.amount if tax_currency.id == company_currency.id else \
                    tax_currency.with_context(date=invoice.date_invoice).compute(tax.amount, tax_currency)
                SubElement(tax_amount_element, 'Amount').text = float_to_str(abs(tax_amount_company))
                if tax_currency.id != company_currency.id:
                    SubElement(tax_amount_element, 'CurrencyCode').text = tax_currency.name
                    SubElement(tax_amount_element, 'CurrencyAmount').text = float_to_str(abs(tax.amount))

        SubElement(document_totals, 'NetTotal').text = float_to_str(abs(invoice.amount_untaxed_signed))
        SubElement(document_totals, 'GrossTotal').text = float_to_str(abs(invoice.amount_total_company_signed))

    @api.model
    def get_company_structure(self, element, partner):
        """
        CompanyStructure element
        """
        SubElement(element, 'RegistrationNumber').text = partner.kodas
        SubElement(element, 'Name').text = partner.name[:70]
        address = SubElement(element, 'Address')
        self.get_address_structure(address, partner)

        partner_country_code = partner.country_id.code
        if partner_country_code != 'LT' and partner.vat:
            tax_registration = SubElement(element, 'TaxRegistration')
            SubElement(tax_registration, 'TaxRegistrationNumber').text = partner.vat
            SubElement(tax_registration, 'TaxType').text = 'PVM'
            SubElement(tax_registration, 'Country').text = partner_country_code

        partner_bank_accounts = self.env['res.partner.bank'].search([('partner_id', '=', partner.id)])
        for bank_account in partner_bank_accounts:
            bank_account_element = SubElement(element, 'BankAccount')
            self.get_bank_account_structure(bank_account_element, bank_account.acc_number)

    """Other"""

    @api.model
    def get_product_domain(self):
        return [('robo_product', '=', False), ('landed_cost_ok', '=', False), ('default_code', '!=', False)]

    @api.model
    def get_stock_data(self, product_ids, location_ids, date):
        """
        Get stock data from stock history
        :param product_ids: A list of product IDS to get stock history for
        :param location_ids: A list of location IDS to get stock history for
        :param date: A date to get stock history for
        :return: A list of stock data grouped by product_id and location_id containing quantity and value
        """
        domain = [('product_id', 'in', product_ids), ('location_id', 'in', location_ids), ('date', '<=', date)]
        select_fields = ['product_id', 'location_id', 'quantity', 'total_value']
        group_by = ['product_id', 'location_id']
        stock_data = self.sudo().env['stock.history'].read_group(domain, select_fields, group_by, lazy=False)
        return stock_data

    @api.multi
    def get_related_assets(self):
        """
        Get all assets accounted in the selected period
        :return: Assets
        """
        self.ensure_one()
        # Asset search is done in reference to how assets are selected in turto.sarasas.wizard
        AccountAsset = self.env['account.asset.asset']
        DepreciationLine = self.env['account.asset.depreciation.line']
        assets = DepreciationLine.search([('depreciation_date', '<=', self.date_to),
                                          ('depreciation_date', '>=', self.date_from),
                                          ('move_check', '=', True)]).mapped('asset_id'). \
            filtered(lambda r: r.active and r.state in ['open', 'close'])
        assets |= AccountAsset.search([('state', 'in', ['open', 'close']), ('active', '=', True), '|',
                                       ('pirkimo_data', '<=', self.date_to), ('date', '<=', self.date_to), '|',
                                       ('date', '>=', self.date_from), ('date_close', '>=', self.date_from)])
        return assets

    @api.model
    def get_movement_type(self, picking_type):
        """
        Get type of movement by stock locations from/to
        :param picking_type: stock.picking.type record
        :return: Type of stock move (str)
        """
        customers_location = self.env.ref('stock.stock_location_customers', False)
        if customers_location:
            if picking_type.default_location_src_id.usage == 'internal' and \
                    (not picking_type.default_location_dest_id or picking_type.default_location_dest_id.id ==
                     customers_location.id):
                return 'PARD'  # Sale
            elif picking_type.default_location_src_id.id == customers_location.id and \
                    picking_type.default_location_dest_id.usage == 'internal':
                return 'PG'  # Sale return
        suppliers_location = self.env.ref('stock.stock_location_suppliers', False)
        if suppliers_location:
            if picking_type.default_location_dest_id.usage == 'internal' and \
                    (not picking_type.default_location_src_id or picking_type.default_location_src_id.id ==
                     suppliers_location.id):
                return 'PIR'  # Purchase
            elif picking_type.default_location_dest_id.id == suppliers_location.id and \
                    picking_type.default_location_src_id.usage == 'internal':
                return 'PRG'  # Purchase return
        inventory_location = self.env.ref('stock.location_inventory', False)
        if inventory_location:
            if picking_type.default_location_src_id.usage == 'internal' and \
                    picking_type.default_location_dest_id.id == inventory_location.id:
                return 'N'  # Inventory write-off
            elif picking_type.default_location_src_id.id == inventory_location.id and \
                    picking_type.default_location_dest_id.usage == 'internal':
                return 'NG'  # Surplus
        if picking_type.code == 'internal':
            return 'VP'  # Internal move
        if picking_type.code == 'mrp_operation':
            return 'PP'  # Production
        return 'KT'  # Other

    @api.model
    def get_corresponding_move_line(self, move, move_lines, debit_credit_indicator):
        amount_field = 'debit' if debit_credit_indicator == 'D' else 'credit'
        digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        line = move_lines.filtered(lambda x: x.product_id.id == move.product_id.id
                                             and not tools.float_compare(x.quantity, move.product_uom_qty,
                                                                         precision_digits=digits)
                                             and not tools.float_is_zero(x[amount_field], precision_digits=2))

        return line[0] if line else False
