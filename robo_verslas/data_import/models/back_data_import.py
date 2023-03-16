# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from xlrd import XLRDError
from datetime import datetime
from odoo.api import Environment
from six import iteritems
import threading
import odoo


ALLOWED_TAX_CALC_ERROR = 0.05
STATIC_IN_ACCOUNT_CODE = '4430'
STATIC_OUT_ACCOUNT_CODE = '2410'


FIELD_MAPPING = {
    'invoice_number': 'Sąskaitos numeris',
    'date_invoice': 'Sąskaitos data',
    'date_due': 'Mokėjimo terminas',
    'invoice_type': 'Sąskaitos tipas',
    'sum_wo_vat': 'Suma be PVM',
    'vat_sum': 'PVM suma',
    'sum_w_vat': 'Suma su PVM',
    'invoice_currency': 'Sąskaitos valiuta',
    'partner_name': 'Partnerio pavadinimas',
    'partner_code': 'Partnerio kodas',
    'partner_type': 'Partnerio tipas',
    'partner_vat': 'Partnerio PVM kodas',
    'partner_street': 'Gatvė',
    'partner_city': 'Miestas',
    'partner_zip': 'Pašto kodas',
    'partner_country': 'Šalis',
    'partner_phone': 'Tel. Numeris',
    'partner_mail': 'El. Paštas',
    'partner_tags': 'Žymos',
    'partner_category': 'Kategorija',
    'product_name': 'Produktas',
    'description': 'Aprašymas',
    'price_unit': 'Vnt. kaina',
    'quantity': 'Kiekis',
    'unit_vat': 'Vnt. PVM',
    'vat_code': 'PVM kodas',
    'price_unit_w_vat': 'Vnt. kaina su PVM',
    'analytic_code': 'Analitinis kodas',
    'payer': 'Mokėtojas',
    'payment_currency': 'Mokėjimo valiuta',
    'payment_sum': 'Mokėjimo suma',
    'payment_date': 'Mokėjimo data',
    'payment_ref': 'Įmokos kodas',
    'payment_name': 'Mokėjimo pavadinimas',
    'journal_code': 'Žurnalo kodas',
    'journal_name': 'Žurnalo pavadinimas',
    'account_code': 'Buhal. sąskaitos kodas',
    'location': 'Lokacija',
    'use_credit': 'Naudoti kreditą',
    'force_dates': 'Priverstinės sąskaitos datos',
    'comment': 'Pastabos',
}

FIELD_LIST = ['invoice_number', 'date_invoice', 'date_due', 'invoice_type',
              'sum_wo_vat', 'vat_sum', 'sum_w_vat', 'invoice_currency', 'partner_name',
              'partner_code', 'partner_type', 'partner_vat',
              'partner_street', 'partner_city', 'partner_zip', 'partner_country', 'partner_phone',
              'partner_mail', 'partner_tags', 'partner_category', 'product_name', 'description',
              'price_unit', 'quantity', 'unit_vat', 'vat_code', 'price_unit_w_vat', 'analytic_code', 'payer',
              'payment_currency', 'payment_sum', 'payment_date', 'payment_ref',
              'payment_name', 'journal_code', 'journal_name', 'account_code', 'location', 'use_credit', 'force_dates',
              'comment']

REQUIRED_FIELD_MAPPING = ['invoice_number', 'date_invoice', 'sum_wo_vat', 'partner_name', 'invoice_type']

CONDITIONALLY_REQUIRED_FIELD_MAPPING = {
    'payer': ['payment_sum', 'payment_date', 'journal_code', 'journal_name'],
    'product_name': ['price_unit', 'quantity', 'description'],
}


FLOAT_MAPPING = ['sum_wo_vat', 'vat_sum', 'sum_w_vat', 'price_unit',
                 'quantity', 'unit_vat', 'price_unit_w_vat', 'payment_sum']

STR_MAPPING = ['invoice_type', 'partner_code', 'zip', 'invoice_number', 'analytic_code', 'account_code']

BOOL_MAPPING = ['force_dates', 'use_credit']

INVOICE_TYPE_MAPPING = {
    '1': 'out_invoice',
    '2': 'out_refund',
    '3': 'out_invoice_prof',
    '4': 'out_refund_prof',
    '5': 'in_invoice',
    '6': 'in_refund',
    '7': 'in_invoice_prof',
    '8': 'in_refund_prof'
}

IN_INVOICE_TYPES = ['5', '6', '7', '8']


class BackDataImport(models.TransientModel):

    _name = 'back.data.import'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)
    check_amounts = fields.Boolean(string='Tikrinti sumas', default=True)

    @api.multi
    def data_import(self):
        """
        Read data from XLS file and prepare it for further account.invoice creation
        :return: None
        """
        self.ensure_one()
        data = self.xls_data
        record_set = []
        invoice_identification = []
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
                if field in ['date_invoice', 'date_due', 'payment_date'] and value:
                    try:
                        if isinstance(value, basestring):
                            # Check the format by trying to convert to datetime object
                            datetime.strptime(value, tools.DEFAULT_SERVER_DATE_FORMAT)
                        else:
                            value = datetime(
                                *xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    except Exception as e:
                        raise exceptions.UserError(_('Netinkamas failo datos formatas! Klaida %s') % e.args[0])

                if field == 'invoice_type' and value:
                    try:
                        value = str(int(value))
                    except (UnicodeEncodeError, ValueError):
                        raise exceptions.UserError(_('Netinkama sąskaitos tipo reikšmė: %s. Eilutė - %s.') % (
                            value, str(row + 1)))

                if field == 'partner_type' and (not value or value == 'COM'):
                    partner_code = record.get('partner_code')
                    try:
                        str(int(partner_code))
                    except (UnicodeEncodeError, ValueError):
                        raise exceptions.UserError(
                            _('Netinkama partnerio kodo reikšmė: %s. Eilutė - %s.') % (
                                value, str(row + 1)))

                # General required field checks
                if field in REQUIRED_FIELD_MAPPING and not value and not isinstance(value, (int, float)):
                    raise exceptions.UserError(
                        _('Nerasta reikšmė privalomam laukui: %s. Eilutė - %s') % (
                            FIELD_MAPPING[field], str(row + 1)))

                record[field] = value
                col += 1

            # Conditional field checks
            for field, dependencies in iteritems(CONDITIONALLY_REQUIRED_FIELD_MAPPING):
                if record.get(field):
                    for dependency in dependencies:
                        if not record.get(dependency):
                            raise exceptions.UserError(
                                _('Kai įrašoma lauko %s reikšmė, laukelis %s yra privalomas. Eilutė - %s.') % (
                                    FIELD_MAPPING[field], FIELD_MAPPING[dependency], str(row + 1)))

            identification = {
                'invoice_number': record.get('invoice_number'),
                'partner_name': record.get('partner_name'),
                'partner_code': record.get('partner_code')
            }
            if identification not in invoice_identification:
                invoice_identification.append(identification)
            record_set.append(record)
        structured_data = self.re_arrange_data(record_set, invoice_identification)
        self.validator(structured_data)

        active_jobs = self.env['back.data.import.job'].search([('state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.UserError(_('Negalite atlikti šio veiksmo, XLS failas yra importuojamas šiuo metu!'))

        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'imported_file_name': self.xls_name
        }
        job_id = self.env['back.data.import.job'].create(vals)
        self.env.cr.commit()
        threaded_calculation = threading.Thread(target=self.data_import_thread,
                                                args=(structured_data, job_id.id, self.id, ))
        threaded_calculation.start()

    @api.model
    def re_arrange_data(self, data, invoice_identification):
        """
        Re-organize data so every line with the same invoice number or a combination of
        invoice number/partner name/partner code (depending on invoice type) is interpreted as invoice lines
        of the same invoice
        :param data: invoice data
        :param invoice_identification: a list of dictionaries containing unique invoice identification -
        a combination of invoice number, partner name and partner code
        :return: structured data, format  - [{}, {}...]
        """
        structured_data = []
        for identification in invoice_identification:
            # Invoice must match invoice number
            # In addition expense invoice is combined with partner name and partner code
            invoice_data = [x for x in data
                            if x.get('invoice_number') == identification.get('invoice_number') and
                            ((x.get('partner_name') == identification.get('partner_name') and
                              x.get('partner_code') == identification.get('partner_code'))
                             or x.get('invoice_type') not in IN_INVOICE_TYPES)]
            invoice_lines = []
            payments = []
            computed_amt_total_w_vat = 0.0
            computed_amt_total_wo_vat = 0.0
            computed_amt_total_vat = 0.0
            new_vals = {
                'invoice_lines': invoice_lines,
                'payments': payments,
            }

            for invoice_line in invoice_data:
                # Convert to corresponding types
                self.float_converter(invoice_line)
                self.str_converter(invoice_line)
                self.bool_converter(invoice_line)

            # Update the values after conversions
            new_vals.update(invoice_data[0])

            for line in invoice_data:
                description = line.get('description')
                product_name = line.get('product_name')
                payer = line.get('payer')
                if description or product_name:
                    try:
                        price_w_vat = float(line.get('price_unit_w_vat', 0))
                        quantity = float(line.get('quantity', 0))
                        price_unit = float(line.get('price_unit', 0))
                        unit_vat = float(line.get('unit_vat', 0))
                    except ValueError:
                        raise exceptions.UserError(
                            _('Klaidingos skaitinės reikšmės sąskaitos eilutės sekcijoje. Eilutė - %s') % (
                                line['row_number']))
                    line_total_w_vat = price_w_vat * quantity
                    line_total_wo_vat = price_unit * quantity
                    line_total_vat = unit_vat * quantity
                    vals = {
                        'description': description,
                        'product_name': product_name,
                        'quantity': quantity,
                        'price_unit': price_unit,
                        'vat_code': line.get('vat_code'),
                        'unit_vat': unit_vat,
                        'price_unit_w_vat': price_w_vat,
                        'line_sum_w_vat': line_total_w_vat,
                        'row_number': new_vals.get('row_number')
                    }
                    invoice_lines.append(vals)
                    computed_amt_total_w_vat += line_total_w_vat
                    computed_amt_total_wo_vat += line_total_wo_vat
                    computed_amt_total_vat += line_total_vat
                if payer:
                    try:
                        payment_sum = float(line.get('payment_sum', 0))
                    except ValueError:
                        raise exceptions.UserError(
                            _('Klaidinga mokėjimo sumos skaitinė reikšmė. Eilutė - %s') % (
                                line['row_number']))
                    vals = {
                        'payer': payer,
                        'payment_sum': payment_sum,
                        'payment_date': line.get('payment_date'),
                        'journal_code': line.get('journal_code'),
                        'journal_name': line.get('journal_name'),
                        'payment_name': line.get('payment_name'),
                        'payment_ref': line.get('payment_ref')
                    }
                    payments.append(vals)

            # Sanity checks
            if not invoice_lines:
                raise exceptions.UserError(
                    _('Nepateikta informacija apie sąskaitos eilutes. Eilutė - %s') % (
                        new_vals['row_number']))

            # If total amount with vat is zero, compose it from vat and w/o vat amounts
            if tools.float_is_zero(computed_amt_total_w_vat, precision_digits=2):
                computed_amt_total_w_vat = computed_amt_total_vat + computed_amt_total_wo_vat

            if tools.float_compare(computed_amt_total_w_vat, new_vals['sum_w_vat'], precision_digits=2) != 0:
                raise exceptions.UserError(
                    _('Pateikta sąskaitos suma su PVM neatitinka bendros eilučių sumos. Eilutė - %s') % (
                        new_vals['row_number']))
            if tools.float_compare(computed_amt_total_wo_vat, new_vals['sum_wo_vat'], precision_digits=2) != 0:
                raise exceptions.UserError(
                    _('Pateikta sąskaitos suma be PVM neatitinka bendros eilučių sumos. Eilutė - %s') % (
                        new_vals['row_number']))
            if tools.float_compare(computed_amt_total_vat, new_vals['vat_sum'], precision_digits=2) != 0:
                raise exceptions.UserError(
                    _('Pateikta sąskaitos PVM suma neatitinka bendros eilučių sumos. Eilutė - %s') % (
                        new_vals['row_number']))
            new_vals.update({
                'amount_invoice_total': computed_amt_total_w_vat,
                'amount_invoice_untaxed': computed_amt_total_wo_vat,
                'amount_invoice_tax': computed_amt_total_vat
            })
            structured_data.append(new_vals)
        return structured_data

    @api.multi
    def data_import_thread(self, record_set, job_id, import_id):
        """
        Create account.invoices using XLS data // THREADED
        :param record_set: XLS data. Format - [{}, {}...]
        :param job_id: back.data.import.job ID
        :param import_id: Calling object ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_obj = env['back.data.import.job'].browse(job_id)
            import_obj = env['back.data.import'].browse(import_id)
            invoice_ids = env['account.invoice']
            try:
                for rec in record_set:
                    move_name = rec.get('invoice_number', str())
                    invoice = env['account.invoice'].search([('move_name', '=', move_name)])
                    if invoice:
                        if not invoice.payment_move_line_ids:
                            import_obj.create_moves(rec, invoice)
                        continue
                    invoice = import_obj.create_invoice(rec)
                    invoice_ids |= invoice
            except Exception as exc:
                new_cr.rollback()
                job_obj.write({'state': 'failed',
                               'fail_message': str(exc.args[0]),
                               'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_obj.write({'state': 'finished',
                               'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                               'created_ids': [(6, 0, invoice_ids.ids)]})
            new_cr.commit()
            new_cr.close()

    @api.model
    def validator(self, data_set):
        """
        Validate whether passed data fields pass all of the constraints
        :param data_set: XLS data set
        :return: None
        """
        for data in data_set:
            body = str()
            payments = data.get('payments', [])
            for payment in payments:
                payment_journal_code = payment.get('journal_code', str())
                if len(payment_journal_code) > 5:
                    body += _('Apmokėjimo žurnalo kodas viršija 4 simbolius\n')
                if not payment_journal_code.isupper():
                    body += _('Apmokėjimo žurnalo kodas turėtų būti iš didžiųjų raidžių\n')

            # Try to parse the invoice type
            try:
                invoice_type = INVOICE_TYPE_MAPPING.get(str(int(data.get('invoice_type'))))
            except (TypeError, ValueError):
                invoice_type = None
            if not invoice_type:
                body += _('Nurodytas klaidingas sąskaitos tipas\n')
            if body:
                body += _('Sąskaitos kūrimo klaida | %s eilutė Excel faile |') % data.get('row_number')
                raise exceptions.UserError(body)

    @api.model
    def create_invoice(self, data):
        """
        Create account.invoice record from passed XLS data
        :param data: invoice data, dict()
        :return: created account.invoice record
        """
        proforma = False
        invoice_obj = self.env['account.invoice'].sudo()

        invoice_type = INVOICE_TYPE_MAPPING.get(data.get('invoice_type'))
        if 'prof' in invoice_type:
            proforma = True
            invoice_type = invoice_type.replace('_prof', '')

        in_invoice = int(data.get('invoice_type') or 0) >= 5

        # Get records-to use
        account = self.get_account(data)
        partner = self.get_partner(data)
        analytic = self.get_analytic(data)
        currency = self.get_currency(data)
        invoice_category = self.get_invoice_category(data)

        default_journal = self.env['account.journal'].search([('type', '=', invoice_category)], limit=1)
        date_invoice = data.get('date_invoice')
        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'account_id': account.id,
            'partner_id': partner.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'reference' if in_invoice else 'number': data.get('invoice_number'),
            'force_dates': data.get('force_dates'),
            'move_name': data.get('invoice_number') if not in_invoice else False,
            'date_invoice': date_invoice,
            'operacijos_data': date_invoice,
            'imported_api': True,
            'currency_id': currency.id,
            'comment': data.get('comment'),
        }

        date_due = data.get('date_due')
        if date_due:
            invoice_values['date_due'] = date_due

        amount_invoice_total = data.get('amount_invoice_total')
        amount_invoice_untaxed = data.get('amount_invoice_untaxed')
        amount_invoice_tax = data.get('amount_invoice_tax')

        price_include = False
        for line in data.get('invoice_lines'):
            product_id = self.get_product(line)

            # Get prices/quantities
            price_unit_w_vat = line.get('price_unit_w_vat', 0)
            if price_unit_w_vat and not tools.float_is_zero(price_unit_w_vat, precision_digits=2):
                price_include = True
            elif price_include:
                raise exceptions.UserError(_('Sąskaitos kūrimo klaida | %s eilutė Excel faile | Klaidos pranešimas %s') % (
                    data.get('row_number'), _('Either all lines should provide price unit with VAT, or none.')))

            tax_id = self.with_context(date=date_invoice).get_tax(line, price_include, invoice_category)
            price_unit = price_unit_w_vat if price_include else line.get('price_unit')
            quantity = line.get('quantity')

            if in_invoice:
                product_account = product_id.get_product_expense_account(return_default=True)
            else:
                product_account = product_id.get_product_income_account(return_default=True)

            line_vals = {
                'product_id': product_id.id,
                'name': line.get('description') or product_id.name,
                'quantity': quantity,
                'price_unit': price_unit,
                'account_id': product_account.id,
                'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                'account_analytic_id': analytic.id,
            }
            invoice_lines.append((0, 0, line_vals))
        invoice_values['price_include_selection'] = 'inc' if price_include else 'exc'
        try:
            invoice_id = invoice_obj.create(invoice_values)
        except Exception as e:
            raise exceptions.UserError(
                _('Sąskaitos kūrimo klaida | %s eilutė Excel faile | Klaidos pranešimas %s') % (
                    data.get('row_number'), e.args[0]))

        if self.check_amounts:
            body = str()
            if not tools.float_is_zero(amount_invoice_total, precision_digits=2) and tools.float_compare(
                    amount_invoice_total, invoice_id.reporting_amount_total, precision_digits=2) != 0:
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos galutinė suma nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (amount_invoice_total, invoice_id.reporting_amount_total, data.get('row_number'))

            if not tools.float_is_zero(amount_invoice_untaxed, precision_digits=2) and tools.float_compare(
                    amount_invoice_untaxed, invoice_id.reporting_amount_untaxed, precision_digits=2) != 0:
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos suma be PVM nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (amount_invoice_untaxed, invoice_id.reporting_amount_untaxed, data.get('row_number'))

            if not tools.float_is_zero(amount_invoice_tax, precision_digits=2) and tools.float_compare(
                    amount_invoice_tax, invoice_id.reporting_amount_tax, precision_digits=2) != 0:
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos PVM suma nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (amount_invoice_tax, invoice_id.reporting_amount_tax, data.get('row_number'))
            if body:
                raise exceptions.UserError(_(body))

        invoice_id.partner_data_force()
        if proforma:
            invoice_id.action_invoice_proforma2()
        else:
            invoice_id.with_context(skip_attachments=True).action_invoice_open()
            self.create_moves(data, invoice_id)
            self.create_delivery(data, invoice_id)
        return invoice_id

    @api.model
    def create_moves(self, data, invoice):
        """
        Create account.moves for specific invoice passed in the XLS based on payments
        :param data: data from XLS (dict)
        :param invoice: account.invoice (single record)
        :return: None
        """
        journal_obj = self.env['account.journal'].sudo()
        currency_obj = self.env['res.currency'].sudo()
        company_id = self.env.user.company_id

        payments = data.get('payments', [])
        for payment in payments:
            payment_journal_code = payment.get('journal_code', 'CARD')
            payment_journal_name = payment.get('journal_name', 'Payments')
            payment_journal_id = journal_obj.search(
                [('code', '=', payment_journal_code), ('type', '=', 'bank')], limit=1)
            if not payment_journal_id:
                if not payment_journal_name:
                    continue
                if journal_obj.search_count([('name', '=', payment_journal_name)]):
                    raise exceptions.UserError(_('Nepavyko sukurti apmokėjimo. Žurnalas su kodu "%s", nerastas, '
                                                 'tačiau pavadinimas "%s" yra jau naudojamas. '
                                                 'Pasirinkite kitą žurnalo pavadinimą | Eilutės nr: %s') % (
                        payment_journal_code, payment_journal_name, data.get('row_number')))
                payment_journal_id = journal_obj.create({
                    'name': payment_journal_name,
                    'code': payment_journal_code,
                    'type': 'bank',
                })
            if not payment_journal_id:
                raise exceptions.UserError(
                    _('Nepavyko sukurti apmokėjimo žurnalo | Eilutės nr: %s') % data.get('row_number'))

            payer = payment.get('payer')
            payment_amount = abs(payment.get('payment_sum', 0))
            date = payment.get('payment_date')

            # Check currency
            payment_currency_id = payment.get('payment_currency')
            payment_amount_currency = 0.0
            if 'currency' in payment and payment['currency'] != company_id.currency_id.name:
                payment_currency_id = currency_obj.search([('name', '=', payment['currency'])], limit=1)
                if payment_currency_id:
                    payment_amount_currency = payment_amount
                    payment_amount = payment_currency_id.with_context(date=date).compute(payment_amount, company_id.currency_id)
                else:
                    raise exceptions.UserError(
                        _('Nerasta nurodyta apmokėjimo valiuta | Eilutės nr: %s') % data.get('row_number'))

            ref = 'Apmokėjo {} - {}'.format(payer, payment.get('ref') or invoice.number)
            name = payment.get('name') or 'Mokėjimas {}'.format(payer)
            move_lines = []

            debit_line = {
                'name': name,
                'account_id': invoice.account_id.id,
                'date': date
            }
            credit_line = debit_line.copy()

            if payment_currency_id:
                debit_line['currency_id'] = credit_line['currency_id'] = payment_currency_id.id
                sign = -1.0 if invoice.type in ['out_invoice', 'in_refund'] else 1.0
                debit_line['amount_currency'] = payment_amount_currency * sign
                credit_line['amount_currency'] = payment_amount_currency * sign * -1

            if invoice.type in ['out_invoice', 'in_refund']:
                debit_line['credit'] = credit_line['debit'] = payment_amount
                debit_line['debit'] = credit_line['credit'] = 0.0
                debit_line['account_id'] = invoice.account_id.id
                credit_line['account_id'] = payment_journal_id.default_debit_account_id.id
            else:
                debit_line['debit'] = credit_line['credit'] = payment_amount
                debit_line['credit'] = credit_line['debit'] = 0.0
                credit_line['account_id'] = payment_journal_id.default_credit_account_id.id
                debit_line['account_id'] = invoice.account_id.id

            move_lines.append((0, 0, debit_line))
            move_lines.append((0, 0, credit_line))
            move_vals = {
                'ref': ref,
                'line_ids': move_lines,
                'journal_id': payment_journal_id.id,
                'date': date,
                'partner_id': invoice.partner_id.id,
            }
            move_id = self.sudo().env['account.move'].create(move_vals)
            move_id.post()
            line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
            line_ids |= invoice.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice.account_id.id)
            if len(line_ids) > 1:
                line_ids.with_context(reconcile_v2=True).reconcile()

        if not tools.float_is_zero(invoice.residual_company_signed, precision_digits=2) and data.get('use_credit'):
            self.reconcile_with_earliest_entries(invoice)

    @api.model
    def create_delivery(self, data, invoice):
        """
        Create delivery for specific invoice passed in the XLS based on passed location
        :param data: data from XLS (dict)
        :param invoice: account.invoice (single record)
        :return: None
        """
        stock_installed = self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', '=', 'installed')])
        if not stock_installed:
            return
        stock_extended = self.env.user.company_id.sudo().politika_sandelio_apskaita == 'extended'
        if stock_extended and any(
                t == 'product' for t in invoice.mapped('invoice_line_ids.product_id.product_tmpl_id.type')):
            location = self.env['stock.location']
            if 'location' in data:
                location_code = data['location']
                warehouse = self.env['stock.warehouse'].search([('code', '=', location_code)])
                location = warehouse.lot_stock_id
                if not warehouse or not location:
                    raise exceptions.UserError(
                        _('Sąskaitos kūrimo klaida, nerasta lokacija | %s eilutė Excel faile') % (
                            data.get('row_number')))
            elif self.env['stock.warehouse'].search([('code', '=', 'WH')], limit=1):
                location = self.env['stock.warehouse'].search([('code', '=', 'WH')], limit=1).lot_stock_id
            elif self.env['stock.warehouse'].search_count([('usage', '=', 'internal')]) == 1:
                location = self.env['stock.warehouse'].search([('usage', '=', 'internal')], limit=1)
            if not location:
                raise exceptions.UserError(
                    _('Sąskaitos kūrimo klaida, nerasta lokacija | %s eilutė Excel faile') % (
                        data.get('row_number')))
            wiz = self.env['invoice.delivery.wizard'].with_context({'invoice_id': invoice.id}).create({
                'location_id': location.id,
            })
            wiz.create_delivery()
            if invoice.picking_id:
                invoice.picking_id.action_assign()
                if invoice.picking_id.shipping_type == 'return':
                    invoice.picking_id.force_assign()
                if invoice.picking_id.state == 'assigned':
                    invoice.picking_id.do_transfer()

    @api.model
    def reconcile_with_earliest_entries(self, invoice):
        """
        If use_credit option is True in create_invoice/update_invoice,
        search for related partner over-payments and try to reconcile the invoice
        with them starting from the oldest payment
        :param invoice: invoice to reconcile
        :return: None
        """
        domain = [('account_id', '=', invoice.account_id.id),
                  ('partner_id', '=', invoice.partner_id.id),
                  ('reconciled', '=', False), ('amount_residual', '!=', 0.0)]
        if invoice.type in ('out_invoice', 'in_refund'):
            domain.extend([('credit', '>', 0), ('debit', '=', 0)])
        else:
            domain.extend([('credit', '=', 0), ('debit', '>', 0)])
        line_ids = self.env['account.move.line'].search(domain, order='date asc')

        for line in line_ids:
            lines = line
            if not tools.float_is_zero(invoice.residual_company_signed, precision_digits=2):
                lines |= invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == invoice.account_id.id)
                if len(lines) > 1:
                    lines.with_context(reconcile_v2=True).reconcile()

    # Getters ---------------------------------------------------------------------------------------------------

    @api.model
    def get_currency(self, data):
        """
        Search for currency record based on passed code.
        If no currency is found, company currency is returned
        :param data: invoice XLS data (dict)
        :return: res.currency (single record)
        """
        currency_code = data.get('invoice_currency')
        currency = None

        # If currency code exists, try to find the currency record, otherwise use company currency
        if currency_code and isinstance(currency_code, basestring):
            sanitized_code = currency_code.strip().upper()
            currency = self.env['res.currency'].search([('name', '=', sanitized_code)], limit=1)
        if not currency:
            currency = self.sudo().env.user.company_id.currency_id
        return currency

    @api.model
    def get_partner(self, data):
        """
        Search for related res.partner record, if not found, create one from passed data
        :param data: invoice XLS data (dict)
        :return: res.partner (single record)
        """
        name = data.get('partner_name')
        code = data.get('partner_code')
        partner_id = self.env['res.partner'].search([('name', '=', name)])
        if (not partner_id or len(partner_id) > 1) and code:
            partner_id = self.env['res.partner'].search([('kodas', '=', code)])
        if not partner_id:
            country_code = data.get('partner_country')
            country_id = self.env['res.country'].sudo().search([('code', '=', country_code)], limit=1)
            if not country_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
            try:
                partner_vals = {
                    'name': name,
                    'is_company': True if data.get('partner_type') == 'COM' else False,
                    'kodas': code,
                    'country_id': country_id.id,
                    'vat': data.get('partner_vat'),
                    'street': data.get('partner_street'),
                    'city': data.get('partner_city'),
                    'zip': data.get('partner_zip'),
                    'phone': data.get('partner_phone'),
                    'email': data.get('partner_mail'),
                }
                tags = data.get('partner_tags')
                if tags and isinstance(tags, (str, unicode)):
                    tag_ids = []
                    tag_parts = tags.split(',')
                    for tag in tag_parts:
                        part_tag = self.env['res.partner.category'].search([('name', '=', tag)])
                        if part_tag:
                            tag_ids.append((4, part_tag.id))
                        else:
                            tag_ids.append((0, 0, {'name': tag}))
                    partner_vals['category_id'] = tag_ids
                if data.get('partner_category'):
                    part_categ_id = self.env['partner.category'].search(
                        [('name', '=', data.get('partner_category'))])
                    if not part_categ_id:
                        part_categ_id = self.env['partner.category'].create({'name': data.get('partner_category')})
                    partner_vals['partner_category_id'] = part_categ_id.id
                partner_id = self.env['res.partner'].create(partner_vals)
            except Exception as exc:
                raise exceptions.UserError(
                    _('Klaida kuriant partnerį %s! | Eilutės nr: %s') % (exc.args[0], data.get('row_number')))
        if len(partner_id) > 1:
            raise exceptions.UserError(
                _('Rasti keli partnerio %s įrašai! | Eilutės nr: %s') % (name, data.get('row_number')))
        return partner_id

    @api.model
    def get_account(self, data):
        """
        Search for related account.account record, if not found, return default 2410 account
        :param data: invoice XLS data (dict)
        :return: account.account (single record)
        """
        code = data.get('account_code')
        account_id = self.env['account.account']
        if code:
            account_id = self.env['account.account'].search([('code', '=', code)])
        if not account_id:
            code = STATIC_IN_ACCOUNT_CODE if data.get('invoice_type') >= 5 else STATIC_OUT_ACCOUNT_CODE
            account_id = self.env['account.account'].search([('code', '=', code)])
        return account_id

    @api.model
    def get_analytic(self, data):
        """
        Search for related analytic account record, based on code
        :param data: invoice XLS data (dict)
        :return: account.analytic.account (single record)
        """
        code = data.get('analytic_code')
        analytic_acc = self.env['account.analytic.account']
        if code:
            analytic_acc = analytic_acc.search([('code', '=', code)])
        return analytic_acc

    @api.model
    def get_product(self, data):
        """
        :param data: invoice XLS data (dict)
        :return: product.product (record/empty-set)
        """
        product_name = data.get('product_name')
        product = self.env['product.product']
        if product_name:
            product = product.search([('name', '=', product_name)])
            if not product:
                product = product.search([('default_code', '=', product_name)])
                if not product:
                    raise exceptions.UserError(
                        _('Sąskaitos kūrimo klaida | %s eilutė Excel faile | Produktas nerastas sistemoje') % (
                            data.get('row_number')))
                if len(product) > 1:
                    raise exceptions.UserError(
                        _('Sąskaitos kūrimo klaida | %s eilutė Excel faile | '
                          'Rasti keli produktai su tuo pačiu kodu') % (data.get('row_number')))
        return product

    @api.model
    def get_tax(self, data, price_include, type_tax_use):
        """
        Search for related account.tax record in the system, based on code, or percentage
        :param data: invoice XLS data (dict)
        :param price_include: Indicates whether related account.tax record amount is included in price
        :param type_tax_use: Either 'sale' or 'purchase, indicates tax type (str)
        :return: account.tax (record/empty-set)
        """
        invoice_vat_code = data.get('vat_code')
        account_tax = self.env['account.tax']
        # If company is vat payer and there's no vat code, raise an error
        if not invoice_vat_code and self.env.user.company_id.vat_payer:
            raise exceptions.UserError(
                _('Sąskaitos kūrimo klaida, nepaduotas PVM kodas | %s eilutė Excel faile') % (
                    data.get('row_number')))

        if invoice_vat_code:
            if ' ' not in invoice_vat_code:
                invoice_vat_code = invoice_vat_code.upper()
            if invoice_vat_code[-1] == 'N':
                invoice_vat_code = invoice_vat_code[:-1]
                nondeductible = True
            else:
                nondeductible = False
            if invoice_vat_code.endswith('NP'):
                invoice_vat_code = invoice_vat_code[:-2]
                nondeductible_profit = True
                nondeductible = True
            else:
                nondeductible_profit = False

            account_tax = account_tax.search([
                ('nondeductible', '=', nondeductible),
                ('nondeductible_profit', '=', nondeductible_profit),
                ('type_tax_use', '=', type_tax_use),
                ('price_include', '=', price_include),
                ('code', '=', invoice_vat_code)], limit=1)
            if not account_tax:
                raise exceptions.UserError(
                    _('Sąskaitos kūrimo klaida | %s eilutė Excel faile | '
                      'Paduotas neteisingas arba sistemoje neegzistuojantis PVM kodas') % (data.get('row_number')))

        return account_tax

    @api.model
    def get_invoice_category(self, data):
        """
        :param data: invoice XLS data (dict)
        :return: invoice base type (str)
        """
        return 'sale' if data.get('invoice_type') in ['1', '2', '3', '4'] else 'purchase'

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
                        _('Klaidingos skaitinės reikšmė laukui %s. Eilutė - %s') % (
                            FIELD_MAPPING[key], data['row_number']))

    @api.model
    def str_converter(self, data):
        """
        Convert passed data field values to str based on static value list
        :param data: XLS data set
        :return: None
        """
        for key, field in iteritems(data):
            if key in STR_MAPPING:
                try:
                    data[key] = str(int(field))
                except ValueError:
                    try:
                        data[key] = str(field)
                    except ValueError:
                        raise exceptions.UserError(
                            _('Klaidinga reikšmė laukui %s. Eilutė - %s') % (
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
                        _('Klaidinga reikšmė laukui %s. Eilutė - %s') % (
                            FIELD_MAPPING[key], data['row_number']))
                elif field.lower() == 'taip':
                    data[key] = True
                else:
                    data[key] = False
