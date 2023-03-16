# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from lxml import etree
import base64
from datetime import datetime
import logging
from odoo.api import Environment
import threading
import odoo
import xlrd
from xlrd import XLRDError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


# Constant variables -----------------------------------------------------------------------------
TYPE_MAPPER = {
    '01': 'out_refund',
    '00': 'out_invoice'
}
LINES_TO_SKIP = ['advance used']
EXPENSES_INDICATOR = 'expense'
ALLOWED_TAX_CALC_ERROR = 0.1
STATIC_NON_SKIP_IDENTIFIER = '*'


class CSIDataImport(models.TransientModel):
    _name = 'csi.data.import'

    xml_data = fields.Binary(string='XML failas', required=False)
    xml_name = fields.Char(string='XML failo pavadinimas', size=128, required=False)

    xls_data = fields.Binary(string='Excel failas', required=False)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)

    @api.multi
    def xls_checking(self):
        self.ensure_one()
        if not self.xls_data:
            raise exceptions.Warning(_('Nepaduotas failas!'))
        field_list = ['invoice_number', 'date_invoice', 'amount_tax', 'amount_total', 'state']
        record_set = []
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(self.xls_data))
        except XLRDError:
            raise exceptions.Warning(_('Netinkamas failo formatas!'))
        sheet = wb.sheets()[0]
        try:
            for row in range(sheet.nrows):
                if row == 0:
                    continue
                col = 0
                record = {'row_number': str(row + 1)}
                for field in field_list:
                    try:
                        value = sheet.cell(row, col).value
                    except IndexError:
                        value = False
                    if field == 'date_invoice' and value:
                        try:
                            value = datetime(*xlrd.xldate_as_tuple(
                                value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        except Exception as e:
                            raise exceptions.UserError(_('Netinkamas Excel formatas! Prašome paduoti duomenis su '
                                                         'šiomis stulpelių reikšmėmis: sąskaitos numeris, '
                                                         'sąskaitos data, PVM suma, bendra suma ir būsena. '
                                                         'Klaidos pranešimas: %s' % e.args[0]))
                    record[field] = value
                    col += 1
                record_set.append(record)
        except Exception as e:
            raise exceptions.UserError(_('Netinkamas Excel formatas! Prašome paduoti duomenis su šiomis '
                                         'stulpelių reikšmėmis: sąskaitos numeris, sąskaitos data,'
                                         ' PVM suma, bendra suma ir būsena.'
                                         'Klaidos pranešimas: %s' % e.args[0]))
        if self._context.get('fix_data', False):
            active_jobs = self.env['csi.jobs'].search([('operation_code', '=', 'data_fixing'),
                                                       ('state', '=', 'in_progress')])
            if active_jobs:
                raise exceptions.UserError(
                    _('Negalite atlikti šio veiksmo, šio tipo operacija yra atliekama šiuo metu!'))
            vals = {
                'operation_code': 'data_fixing',
                'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'state': 'in_progress'
            }
            job_id = self.env['csi.jobs'].create(vals)
            threaded_calculation = threading.Thread(target=self.fix_data, args=(record_set, job_id.id))
            threaded_calculation.start()
        else:
            self.check_differences(record_set)

    @api.multi
    def check_differences(self, record_set):
        self.ensure_one()
        error_block = str()
        for record in record_set:
            inv_number = record.get('invoice_number')
            inv = self.env['account.invoice'].search(['|', '|', ('number', '=', inv_number),
                                                      ('move_name', '=', inv_number),
                                                      ('reference', '=', inv_number)])
            if not inv:
                msg = 'NOT FOUND: Number - %s\n' % inv_number
                error_block += msg
            else:
                date_invoice = record.get('date_invoice')
                amount_tax = float(record.get('amount_tax', 0.0))
                amount_total = float(record.get('amount_total', 0.0))
                # sanitize state
                state = 'open' if record.get('state', '') in ['Paid', 'Send'] else 'cancel'
                if inv.state in ['open'] and state in ['cancel', 'draft']:
                    msg = 'WRONG STATES: Number - %s. System - %s / XLS - %s \n' % (inv_number,
                                                                                  inv.state, state)
                    error_block += msg
                if inv.date_invoice != date_invoice:
                    msg = 'WRONG DATE: Number - %s. System - %s / XLS - %s \n' % (inv_number,
                                                                                  inv.date_invoice, date_invoice)
                    error_block += msg

                system_amt = abs(tools.float_round(inv.amount_tax, precision_digits=2))
                xls_amt = abs(tools.float_round(amount_tax, precision_digits=2))
                diff = abs(system_amt - xls_amt)
                if tools.float_compare(system_amt, xls_amt, precision_digits=2) != 0 and diff > 0.1:
                    msg = 'WRONG TAX AMT: Number - %s. System - %s / XLS - %s \n' % (inv_number,
                                                                                     system_amt, xls_amt)
                    error_block += msg

                system_amt = abs(tools.float_round(inv.amount_total, precision_digits=2))
                xls_amt = abs(tools.float_round(amount_total, precision_digits=2))
                diff = abs(system_amt - xls_amt)
                if tools.float_compare(xls_amt, system_amt, precision_digits=2) != 0 and diff > 0.1:
                    msg = 'WRONG TOTAL AMT: Number - %s. System - %s / XLS - %s \n' % (inv_number,
                                                                                       system_amt, xls_amt)
                    error_block += msg
        if error_block:
            raise exceptions.UserError(error_block)
        else:
            raise exceptions.UserError('Success, no errors!')

    @api.multi
    def fix_data(self, record_set, job_id):
        self.ensure_one()
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_id = env['csi.jobs'].browse(job_id)
            try:
                for record in record_set:
                    inv_number = record.get('invoice_number')
                    inv = env['account.invoice'].search(['|', '|', ('number', '=', inv_number),
                                                              ('move_name', '=', inv_number),
                                                              ('reference', '=', inv_number)])
                    if not inv:
                        continue
                    date_invoice = record.get('date_invoice')
                    if inv.date_invoice != date_invoice:
                        if inv.state in ['draft']:
                            inv.write({'date_invoice': date_invoice})
                        else:
                            inv.action_invoice_cancel_draft()
                            inv.write({'date_invoice': date_invoice})
                            inv.action_invoice_open()
                    state = 'open' if record.get('state', '') in ['Paid', 'Send'] else 'cancel'
                    if inv.state in ['open'] and state in ['cancel']:
                        inv.action_invoice_cancel_draft()
            except Exception as exc:
                new_cr.close()
                job_id.write({'state': 'failed',
                              'fail_message': str(exc.args[0]),
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_id.write({'state': 'finished',
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()

    def xml_parsing(self):

        def get_value(node, tag):
            if node is None:
                return ''
            return node.find(tag).text if node.find(tag) is not None else ''

        if not self.xml_data:
            raise exceptions.ValidationError(_('Nepaduotas failas'))
        data = base64.b64decode(self.xml_data)
        try:
            root = etree.fromstring(data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            raise exceptions.ValidationError(_('Netinkamas failo formatas.'))

        if type(root) != etree._Element:
            raise exceptions.ValidationError(_('Netinkamas failo formatas.'))

        invoices = root.findall('.//CONTENT_FRAME//INVOICES//INVOICE')
        block_id = get_value(root, 'CONTENT_FRAME//BLOCK_ID')

        active_jobs = self.env['csi.jobs'].search([('operation_code', '=', 'data_import'),
                                                   ('state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo operacija yra atliekama šiuo metu!'))
        vals = {
            'operation_code': 'data_import',
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress'
        }
        job_id = self.env['csi.jobs'].create(vals)

        threaded_calculation = threading.Thread(target=self.create_invoices_thread,
                                                args=(invoices, block_id, job_id.id))
        threaded_calculation.start()
        return

    @api.multi
    def create_invoices_thread(self, invoices, block_id, job_id):

        def parse_date(node):
            node = node.find('DATE')
            if node is not None:
                day = get_value(node, 'DAY')
                month = get_value(node, 'MONTH')
                century = get_value(node, 'CENTURY')
                decade = get_value(node, 'DECADE_AND_YEAR')
                if day and month and century and decade:
                    return century + decade + '-' + month + '-' + day
                else:
                    return None
            else:
                return None

        def get_value(node, tag):
            if node is None:
                return ''
            return node.find(tag).text if node.find(tag) is not None else ''

        def convert_sign(value):
            if value is not None:
                sign_value = value.get('SIGN')
                value_float = float(value.text or 0)
                if sign_value == '-':
                    return value_float * -1
                else:
                    return value_float
            else:
                return 0
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_id = env['csi.jobs'].browse(job_id)

            # Initialize variables in the method, so dates are computed in the call
            invoice_prefix = 'WLS' + datetime.now().strftime('%Y')[2:]
            credit_invoice_prefix = 'WLSK' + datetime.now().strftime('%Y')[2:]
            credit_invoice_prefix_ly = 'WLSK' + (datetime.now() - relativedelta(years=1)).strftime('%Y')[2:]
            invoice_prefix_ly = 'WLS' + (datetime.now() - relativedelta(years=1)).strftime('%Y')[2:]

            invoices_to_create_list = []
            created_invoices_list = []

            try:
                potential_skip_list = []
                for index, invoice in enumerate(invoices):
                    _logger.info('CSI Invoice import: %s' % str(index))
                    header = invoice.find('HEADER')

                    # If WLS/WLSK is not in number or no there is no number at all
                    # We check CREDIT_INVOICE_NUMBER value and if it is WLS -- That invoice will be potentially
                    # skipped, unless it has STATIC_NON_SKIP_IDENTIFIER in its name.

                    number = get_value(header, 'INVOICE_ID')
                    credit_number = get_value(header, 'CREDIT_INVOICE_NUMBER')

                    if not number or (
                            invoice_prefix not in number and invoice_prefix_ly not in number and credit_invoice_prefix
                            not in number and credit_invoice_prefix_ly not in number):
                        if credit_number and (invoice_prefix in credit_number or invoice_prefix_ly in credit_number):
                            potential_skip_list.append(credit_number)
                        continue
                    else:
                        sanitized_number = number.replace(STATIC_NON_SKIP_IDENTIFIER, str())
                        if sanitized_number in potential_skip_list or number in potential_skip_list:
                            if STATIC_NON_SKIP_IDENTIFIER not in number:
                                continue
                            else:
                                number = sanitized_number

                    reconcile_with_record = False
                    record = env['account.invoice'].search(['|', ('move_name', '=', number), ('number', '=', number)])
                    credited_record = env['account.invoice'].search(
                        ['|', ('move_name', '=', credit_number), ('number', '=', credit_number)]) \
                        if credit_number else env['account.invoice']

                    if credited_record and not record and (
                                credit_invoice_prefix_ly in number or credit_invoice_prefix in number):
                        if credited_record.state in ['draft']:
                            try:
                                credited_record.partner_data_force()
                                # if we find invoice to be credited in the system, we open it,
                                # and proceed to create corresponding credit invoice
                                credited_record.with_context(force_action_create=True).action_invoice_open()
                            except Exception as e:
                                new_cr.rollback()
                                body = _('Klaida tvirtinant CSI sąskaitą %s. Pranešimas %s') % (number, e)
                                _logger.info(body)
                                continue
                        reconcile_with_record = True
                    elif record:
                        continue

                    invoices_to_create_list.append(number)
                    currency_code = get_value(header, 'CURRENCY//CODE') or 'EUR'
                    invoice_type = get_value(header, 'INVOICE_TYPE')
                    date_invoice = parse_date(header.find('INVOICE_DATE'))
                    date_due = parse_date(header.find('DUE_DATE'))

                    currency_id = env['res.currency'].search([('name', '=', currency_code)])
                    account_id = env['account.account'].search([('code', '=', '2410')])
                    journal_id = env['account.journal'].search([('type', '=', 'sale')], limit=1)

                    partner_node = invoice.find('RECEIVER')
                    part_info = partner_node.find('CUSTOMER_INFORMATION')
                    bank = partner_node.find('BANKS')
                    eu_country = part_info.find('EU-COUNTRY')
                    address = part_info.find('ADDRESS')

                    partner_name = get_value(part_info, 'CUSTOMER_NAME')
                    company_code = get_value(part_info, 'ORGANIZATION_NUMBER')

                    if not company_code:
                        company_code = get_value(part_info, 'TRADE_REGISTRY_NUMBER')
                    partner_code = get_value(part_info, 'SOCIAL_SECURITY_NUMBER')
                    ext_id = get_value(part_info, 'PARTY_IDENTIFICATION_ID')

                    is_company = True if company_code and not partner_code else False
                    part_street = get_value(address, 'STREET_ADDRESS1')
                    part_zip = get_value(address, 'POSTAL_CODE')
                    part_city = get_value(address, 'POST_OFFICE')
                    part_country_code = get_value(eu_country, 'EU_COUNTRY_CODE')
                    if not part_country_code:
                        part_country_code = get_value(address, 'COUNTRY_CODE')
                    country_id = env['res.country'].sudo().search([('code', '=', part_country_code)], limit=1)
                    partner_id = env['res.partner']

                    if ext_id:
                        partner_id = env['res.partner'].search([('csi_ext_id', '=', ext_id)])

                    if company_code and is_company and not partner_id:
                        partner_id = env['res.partner'].search([('kodas', '=', company_code)])

                    if partner_code and not is_company and not partner_id:
                        partner_id = env['res.partner'].search([('kodas', '=', partner_code)])

                    if not partner_id and partner_name:
                        partner_id = env['res.partner'].search([('name', '=', partner_name)])

                    if partner_id and len(partner_id) == 1:
                        if not partner_id.csi_ext_id:
                            partner_id.csi_ext_id = ext_id  # write crashes the thread sometimes, probably timing issues

                    if not partner_id:
                        partner_vals = {
                            'name': partner_name,
                            'is_company': is_company,
                            'kodas': company_code or partner_code,
                            'street': part_street,
                            'city': part_city,
                            'zip': part_zip,
                            'csi_ext_id': ext_id,
                            'country_id': country_id.id,
                            'property_account_receivable_id': env['account.account'].sudo().search(
                                [('code', '=', '2410')], limit=1).id,
                            'property_account_payable_id': env['account.account'].sudo().search(
                                [('code', '=', '4430')], limit=1).id,
                        }
                        partner_id = env['res.partner'].create(partner_vals)

                    if bank:
                        bank_name = get_value(bank, 'BANK_NAME')
                        swift_code = get_value(bank, 'SWIFT_CODE')
                        iban = get_value(bank, 'IBAN_ACCOUNT_NUMBER')
                        bank_id = env['res.bank'].search([('bic', '=', swift_code)])
                        env['res.partner.bank'].create({
                            'bank_name': bank_name,
                            'acc_number': iban.replace(' ', ''),
                            'bank_id': bank_id.id,
                            'currency_id': country_id.currency_id.id,
                            'partner_id': partner_id.id,
                        })
                    if len(partner_id) > 1:
                        partner_id = env['res.partner']
                    type_category = TYPE_MAPPER[invoice_type] if invoice_type else False

                    if not partner_id:
                        body = _('Nerastas CSI partneris, kuriant sąskaitą: %s. Batch ID: %s \n') % (number, block_id)
                        _logger.info(body)
                        continue

                    invoice_lines = []
                    lines = invoice.findall('ROWS//ROW')
                    if not lines:
                        _logger.info('Skipping invoice %s... No lines found' % number)
                        continue
                    skip_total_control_checks = False
                    for line in lines:
                        product_name = get_value(line, 'ARTICLE//ARTICLE_NAME')
                        # Get lowercase name to check against
                        name_to_check = product_name.lower()

                        if name_to_check in LINES_TO_SKIP:
                            skip_total_control_checks = True
                            continue
                        # Check whether current line is expense line or not
                        expense_line = name_to_check and EXPENSES_INDICATOR in name_to_check

                        price_unit = convert_sign(line.find('PRICE_PER_UNIT//AMOUNT'))
                        row_total_no_vat = 0.0
                        row_total_w_vat = 0.0

                        amounts = line.findall('ROW_TOTAL//AMOUNT')
                        for amount in amounts:
                            if amount.get('VAT') == 'EXCLUDED':
                                row_total_no_vat += convert_sign(amount)
                            if amount.get('VAT') == 'INCLUDED':
                                row_total_w_vat += convert_sign(amount)

                        total_sign = 1 if row_total_w_vat >= 0 else -1
                        qty = row_total_no_vat // price_unit if not tools.float_is_zero(price_unit, precision_digits=2) else 1
                        if not type_category:
                            type_category = 'out_invoice' if qty > 0 else 'out_refund'
                        qty = abs(qty)
                        vat_rate = float(get_value(line, 'VAT//RATE') or 0)
                        factual_rate = round(((abs(row_total_w_vat) / abs(row_total_no_vat)) - 1) * 100, 0) if not tools.float_is_zero(row_total_no_vat, precision_digits=2) else vat_rate
                        if abs(abs(vat_rate) - abs(factual_rate)) > 0.1:
                            vat_rate = factual_rate

                        if not vat_rate:
                            vat_code = 'PVM100' if partner_id.country_id.code == 'LT' else 'PVM15'
                            tax_id = env['account.tax'].search([('code', '=', vat_code),
                                                                ('type_tax_use', '=', 'sale'),
                                                                ('price_include', '=', False)], limit=1)

                        else:
                            tax_id = env['account.tax'].search([('amount', '=', vat_rate),
                                                                     ('type_tax_use', '=', 'sale'),
                                                                     ('price_include', '=', False)], limit=1)

                            if not tax_id:
                                percentage = round(((row_total_w_vat / row_total_no_vat) - 1) * 100, 0)
                                tax_id = env['account.tax'].search(
                                    [('amount', '=', percentage), ('type_tax_use', '=', 'sale'),
                                     ('price_include', '=', False)], limit=1).id

                        if not tax_id:
                            body = _('Nerastas CSI PVM kodas eilutėje, kuriant sąskaitą: %s.\n') % number
                            _logger.info(body)
                            continue
                        # If line is expense line, search for expense product, if it's not found continue with
                        # default service product. Template is created instead of product.product
                        # so category can be set accordingly
                        product = env['product.product']
                        if expense_line:
                            product_template = env.ref(
                                'csi.csi_expenses_product_template', raise_if_not_found=False,
                            )
                            if product_template:
                                product = product_template.product_variant_ids[0]
                        if not product:
                            product = env['product.product'].search([('name', '=', 'Paslauga')], limit=1)
                        if not product:
                            product_vals = {
                                'name': product_name,
                                'acc_product_type': 'service',
                                'type': 'service'
                            }
                            product = env['product.product'].create(product_vals)

                        product_account = product.get_product_income_account(return_default=True)
                        unit_converted = price_unit * total_sign if type_category != 'out_refund' else price_unit
                        line = {
                            'product_id': product.id,
                            'name': product_name,
                            'quantity': qty,
                            'price_unit': unit_converted,
                            'uom_id': product.product_tmpl_id.uom_id.id,
                            'account_id': product_account.id,
                            'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                            }
                        invoice_lines.append((0, 0, line))

                    # Create discount lines
                    discount_vat = 0.0
                    discount_lines = invoice.findall('SUMMARY//DISCOUNTS_TOTAL')
                    for line in discount_lines:
                        row_total_no_vat = 0.0
                        row_total_w_vat = 0.0
                        amounts = line.findall('AMOUNT')
                        for amount in amounts:
                            if amount.get('VAT') == 'EXCLUDED':
                                row_total_no_vat += convert_sign(amount)
                            if amount.get('VAT') == 'INCLUDED':
                                row_total_w_vat += convert_sign(amount)

                        if tools.float_is_zero(row_total_no_vat, precision_digits=2):
                            body = _('Nerasta CSI nuolaidos suma kuriant sąskaitą: %s.\n') % number
                            _logger.info(body)
                            continue
                        discount_vat += row_total_w_vat - row_total_no_vat
                        vat_domain = [('type_tax_use', '=', 'sale'), ('price_include', '=', False)]
                        percentage = round(((row_total_w_vat / row_total_no_vat) - 1) * 100, 0)
                        vat_code = 'PVM100' if partner_id.country_id.code == 'LT' else 'PVM15'
                        vat_domain += [('code', '=', vat_code)] if not percentage else [('amount', '=', percentage)]
                        discount_tax_ids = env['account.tax'].search(vat_domain, limit=1).ids

                        if not discount_tax_ids:
                            body = _('Nerastas CSI PVM kodas nuolaidos eilutei kuriant sąskaitą: %s.\n') % number
                            _logger.info(body)
                            continue

                        product_name = _('Nuolaida')
                        product_account_id = env['account.account'].search([('code', '=', '5001')], limit=1).id
                        line = {
                            'name': product_name,
                            'quantity': 1.0,
                            'price_unit': row_total_no_vat,
                            'uom_id': env.ref('product.product_uom_unit').id,
                            'account_id': product_account_id,
                            'invoice_line_tax_ids': [(6, 0, discount_tax_ids)],
                        }
                        invoice_lines.append((0, 0, line))

                    total_wo_vat = 0.0
                    total_w_vat = 0.0
                    total_vat = 0.0

                    vat_summaries = invoice.findall('SUMMARY//VAT_SUMMARY')
                    if skip_total_control_checks:
                        for summary in vat_summaries:
                            total_wo_vat += float(get_value(summary, 'ACCORDING//AMOUNT') or 0)
                    else:
                        total_amounts = invoice.findall('SUMMARY//INVOICE_TOTAL//AMOUNT')
                        for amount in total_amounts:
                            if amount.get('VAT') == 'EXCLUDED':
                                total_wo_vat += convert_sign(amount)
                            if amount.get('VAT') == 'INCLUDED':
                                total_w_vat += convert_sign(amount)
                        total_advance = invoice.findall('SUMMARY//ADVANCE_PAYMENT//AMOUNT')
                        # Ignore the advance already paid, add it to total payable amount
                        for advance in total_advance:
                            if advance.get('VAT') == 'EXCLUDED':
                                total_wo_vat += convert_sign(advance)
                            if advance.get('VAT') == 'INCLUDED':
                                total_w_vat += convert_sign(advance)
                    for summary in vat_summaries:
                        total_vat += float(get_value(summary, 'VAT_RATE_TOTAL//AMOUNT') or 0)

                    # Total VAT is provided excluding discount
                    total_vat += discount_vat

                    invoice_vals = {
                        'move_name': number,
                        'name': number,
                        'date_invoice': date_invoice,
                        'date_due': date_due,
                        'partner_id': partner_id.id,
                        'currency_id': currency_id.id,
                        'invoice_line_ids': invoice_lines,
                        'account_id': account_id.id,
                        'journal_id': journal_id.id,
                        'external_invoice': True,
                        'price_include_selection': 'exc',
                        'type': type_category
                    }
                    try:
                        invoice_id = env['account.invoice'].create(invoice_vals)
                    except Exception as e:
                        new_cr.rollback()
                        body = _('Klaida kuriant CSI sąskaitą %s. Pranešimas %s') % (number, e)
                        _logger.info(body)
                        continue

                    body = str()

                    if tools.float_compare(abs(total_vat), abs(invoice_id.reporting_amount_tax), precision_digits=2):
                        system_sum = abs(invoice_id.amount_tax)
                        ext_sum = abs(total_vat)
                        diff = tools.float_round(ext_sum - system_sum, precision_digits=2)
                        if diff < ALLOWED_TAX_CALC_ERROR:
                            if invoice_id.tax_line_ids:
                                line = invoice_id.invoice_line_ids[0]
                                new_amount = line.amount_depends - diff
                                line.write({
                                    'amount_depends': new_amount,
                                    'price_subtotal_make_force_step': True,
                                    'price_subtotal_save_force_value': new_amount
                                })
                                line.with_context(direct_trigger_amount_depends=True).onchange_amount_depends()
                                invoice_id.write({'force_taxes': True})
                                tax_line = invoice_id.tax_line_ids[0]
                                tax_line.write({'amount': tax_line.amount + diff})
                                if total_vat and tools.float_compare(
                                        abs(total_vat), abs(invoice_id.reporting_amount_tax), precision_digits=2) != 0:
                                    body += _('CSI sąskaitos ir Sukurtos sąskaitos PVM sumos nesutampa: %s != %s, '
                                              'Sąskaitos numeris %s\n') % (
                                        abs(total_vat), abs(invoice_id.reporting_amount_tax), invoice_id.name)
                            else:
                                body += _('CSI sąskaitos ir Sukurtos sąskaitos PVM sumos nesutampa: %s != %s, '
                                          'Sąskaitos numeris %s\n') % (
                                    abs(total_vat), abs(invoice_id.reporting_amount_tax), invoice_id.name)
                        else:
                            body += _('CSI sąskaitos ir Sukurtos sąskaitos PVM sumos nesutampa: %s != %s, '
                                      'Sąskaitos numeris %s\n') % (
                                abs(total_vat), abs(invoice_id.reporting_amount_tax), invoice_id.name)

                    if not skip_total_control_checks:
                        if total_w_vat and tools.float_compare(
                                abs(total_w_vat), abs(invoice_id.reporting_amount_total), precision_digits=2) != 0:
                            diff = tools.float_round(
                                abs(abs(total_w_vat) - abs(invoice_id.reporting_amount_total)), precision_digits=2)
                            if diff > ALLOWED_TAX_CALC_ERROR:
                                body += _('CSI sąskaitos ir Sukurtos sąskaitos galutinės sumos nesutampa: %s != %s, '
                                          'Sąskaitos numeris %s\n') % (
                                    abs(total_w_vat), abs(invoice_id.reporting_amount_total), invoice_id.name)

                    if total_wo_vat and tools.float_compare(
                            abs(total_wo_vat), abs(invoice_id.reporting_amount_untaxed), precision_digits=2) != 0:
                        diff = tools.float_round(
                            abs(abs(total_wo_vat) - abs(invoice_id.reporting_amount_untaxed)), precision_digits=2)
                        if diff > ALLOWED_TAX_CALC_ERROR:
                            body += _('CSI sąskaitos ir Sukurtos sąskaitos sumos be PVM nesutampa: %s != %s, '
                                      'Sąskaitos numeris %s\n') % (
                                abs(total_wo_vat), abs(invoice_id.reporting_amount_untaxed), invoice_id.name)

                    if body:
                        new_cr.rollback()
                        _logger.info(body)
                        continue

                    try:
                        invoice_id.partner_data_force()
                        # already has a move name, since we specify it directly, so we need context
                        invoice_id.with_context(force_action_create=True).action_invoice_open()
                    except Exception as e:
                        new_cr.rollback()
                        body = _('Klaida tvirtinant CSI sąskaitą %s. Pranešimas %s') % (number, e)
                        _logger.info(body)
                        continue
                    if reconcile_with_record and credited_record.state in ['open']:
                        to_be_credited_move_id = credited_record.move_id
                        credit_move_id = invoice_id.move_id
                        account_id = env['account.account'].search([('code', '=', '2410')])
                        line_ids = to_be_credited_move_id.line_ids.filtered(lambda r: r.account_id.id == account_id.id)
                        line_ids |= credit_move_id.line_ids.filtered(
                            lambda r: r.account_id.id == account_id.id)
                        line_ids.with_context(check_move_validity=False).write({'partner_id': invoice_id.partner_id.id})
                        if len(line_ids) > 1:
                            line_ids.with_context(reconcile_v2=True).reconcile()
                    created_invoices_list.append(number)
                    new_cr.commit()

            except Exception as exc:
                job_id.write({'state': 'failed',
                              'fail_message': str(exc.args[0]),
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_id.write({'state': 'finished',
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            invoices_skipped = list(set(invoices_to_create_list) - set(created_invoices_list))
            if invoices_skipped:
                _logger.info('CSI invoices skipped: %s' % str(invoices_skipped))
            _logger.info('CSI import finished')
            new_cr.commit()
            new_cr.close()


CSIDataImport()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    csi_ext_id = fields.Integer(string='Išorinis CSI identifikatorius')


ResPartner()


class CSIJobs(models.Model):
    _name = 'csi.jobs'

    operation_code = fields.Char(string='Operacijos identifikatorius')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')


CSIJobs()
