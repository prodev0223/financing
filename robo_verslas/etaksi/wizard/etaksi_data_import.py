# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from xlrd import XLRDError
from datetime import datetime
import logging
from odoo.api import Environment
import threading
import odoo

_logger = logging.getLogger(__name__)

# Statics -------------------------------------------------------------------------------------------------

allowed_tax_calc_error = 0.01
PAYSERA_CODE = 'ETPSR'
FOX_BOX_CODE = 'ETFBX'

field_list = ['partner_name', 'partner_code', 'invoice_number', 'date_invoice', 'product_name',
              'invoice_line_name', 'analytic_code', 'quantity', 'price_unit', 'vat_rate',
              'amount_total', 'comments', 'report', 'category', 'manager_name',
              'paysera_code', 'paysera_sum', 'fox_box_code', 'fox_box_sum']

required_fields = ['partner_name', 'partner_code', 'invoice_number', 'date_invoice',
                   'invoice_line_name', 'quantity', 'price_unit', 'vat_rate', 'amount_total']

required_field_mapping = {
    'partner_name': 'Pirkėjas',
    'partner_code': 'Pirkėjo kodas',
    'invoice_number': 'Sąskaitos numeris',
    'date_invoice': 'Sąskaitos data',
    'invoice_line_name': 'Paslaugos aprašymas',
    'quantity': 'Kiekis',
    'price_unit': 'Vieneto kaina',
    'vat_rate': 'PVM procentas',
    'amount_total': 'Galutinė suma'
}

NUMERIC_FIELDS = ['partner_code', 'quantity', 'price_unit', 'vat_rate', 'amount_total']


class EtaksiDataImport(models.TransientModel):
    """
    Model used to import XLS file with invoices from client etaksi
    """
    _name = 'etaksi.data.import'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)

    @api.multi
    def data_import_prep(self):
        """
        Read data from passed XLS file, re-arrange it and prepare for threaded
        account.invoice record creation
        :return: None
        """
        self.ensure_one()
        data = self.xls_data
        record_set = []
        invoice_numbers = []
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(data))
        except XLRDError:
            raise exceptions.ValidationError(_('Netinkamas failo formatas'))
        sheet = wb.sheets()[0]
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
                if field in ['date_invoice'] and value:
                    try:
                        value = datetime(
                            *xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    except Exception as e:
                        raise exceptions.ValidationError(_('Netinkamas failo datos formatas! Klaida %s' % e.args[0]))
                if field in NUMERIC_FIELDS and value:
                    try:
                        if field == 'partner_code':
                            value = str(int(value))
                        else:
                            value = float(value)
                    except (UnicodeEncodeError, ValueError):
                        raise exceptions.ValidationError(
                            _('Netinkama lauko - {} reikšmė: "{}". '
                              'Reikšmė šiam laukui privalo būti skaitinė Eilutė - {}.').format(
                                required_field_mapping[field], value, row + 1))
                if field in ['invoice_number'] and value and value not in invoice_numbers:
                    invoice_numbers.append(value)
                if field in required_fields and not value and not isinstance(value, (int, float)):
                    raise exceptions.ValidationError(
                        _('Nerasta reikšmė privalomam laukui: %s. Eilutė - %s' % (
                            required_field_mapping[field], str(row + 1))))
                record[field] = value
                col += 1
            record_set.append(record)
        structured_data = self.re_arrange_data(record_set, invoice_numbers)
        active_jobs = self.env['etaksi.data.import.job'].search([('state', '=', 'in_progress')])
        if active_jobs:
            raise exceptions.ValidationError(_('Negalite atlikti šio veiksmo, XLS failas yra importuojamas šiuo metu!'))

        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'imported_file_name': self.xls_name,
            'imported_file': self.xls_data,
        }
        job_id = self.env['etaksi.data.import.job'].create(vals)
        self.env.cr.commit()
        threaded_calculation = threading.Thread(target=self.data_import_thread,
                                                args=(structured_data, job_id.id,))
        threaded_calculation.start()

    @api.multi
    def data_import_thread(self, record_set, job_id):
        """
        Create account.invoices using XLS data // THREADED
        :param record_set: XLS data. Format - [{}, {}...]
        :param job_id: etaksi.data.import.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job = env['etaksi.data.import.job'].browse(job_id)
            invoices = env['account.invoice']
            import_obj = env['etaksi.data.import']
            try:
                for rec in record_set:
                    partner_code = rec.get('partner_code', str())
                    move_name = rec.get('invoice_number', str())
                    invoice = env['account.invoice'].search([('move_name', '=', move_name)])
                    if invoice:
                        if invoice.partner_id.kodas != partner_code:
                            raise exceptions.ValidationError(
                                _('Sistemoje jau egzistuoja sąskaita su numeriu {}, '
                                  'tačiau XLS kliento kodas skiriasi nuo sisteminio!').format(move_name))
                        # If we find the invoice, and it already has payments we unlink them,
                        # and replace them according to the new info, also we force the new values
                        import_obj.apply_invoice_differences(invoice, rec)
                        if invoice.payment_move_line_ids:
                            import_obj.unlink_move(invoice)
                        import_obj.create_move(invoice, rec)
                        continue
                    invoice = import_obj.create_invoice(rec)
                    import_obj.create_move(invoice, rec)
                    invoices |= invoice
            except Exception as exc:
                new_cr.rollback()
                job.write({'state': 'failed',
                           'fail_message': str(exc.args[0]),
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job.write({'state': 'finished',
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                           'created_ids': [(6, 0, invoices.ids)]})
            new_cr.commit()
            new_cr.close()

    @api.model
    def create_invoice(self, data):
        """
        Create account.invoice record from passed XLS data
        :param data: invoice data, dict()
        :return: created account.invoice record
        """

        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()

        invoice_type = 'out_refund' if data.get('amount_total', 0) < 0 else 'out_invoice'

        # Get records-to use
        account_id = self.env['account.account'].search([('code', '=', '2410')])
        partner_id = self.get_res_partner(data)
        user_id = self.get_res_user(data)
        journal_id = self.get_account_journal(data)

        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'account_id': account_id.id,
            'partner_id': partner_id.id,
            'journal_id': journal_id.id,
            'user_id': user_id.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'inc',
            'number': data.get('invoice_number'),
            'move_name': data.get('invoice_number'),
            'date_invoice': data.get('date_invoice'),
            'operacijos_data': data.get('date_invoice'),
            'imported_api': True,
            'comment': data.get('comments')
        }
        amount_total_invoice = data.get('amount_invoice_total')
        for line in data.get('invoice_lines'):
            product_id = self.get_product(line)
            tax_id = self.get_account_tax(line)
            analytic_account = self.get_analytic_account(line)

            # Get prices/quantities
            price_unit = line.get('price_unit')
            quantity = line.get('quantity')

            product_account = product_id.get_product_income_account(return_default=True)
            line_vals = {
                'product_id': product_id.id,
                'name': line.get('invoice_line_name', ''),
                'quantity': quantity,
                'price_unit': price_unit,
                'account_id': product_account.id,
                'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                'account_analytic_id': analytic_account.id,
            }
            invoice_lines.append((0, 0, line_vals))

        try:
            invoice_id = invoice_obj.create(invoice_values)
        except Exception as e:
            raise exceptions.ValidationError(_('Sąskaitos kūrimo klaida | %s eilutė Excel faile | Klaidos pranešimas %s') %
                                     (data.get('row_number'), e.args[0]))
        body = str()
        if tools.float_compare(amount_total_invoice, abs(invoice_id.reporting_amount_total), precision_digits=2) != 0:
            diff = abs(amount_total_invoice) - abs(invoice_id.reporting_amount_total)
            if -allowed_tax_calc_error < diff < allowed_tax_calc_error:
                if invoice_id.tax_line_ids:
                    invoice_id.write({'force_taxes': True})
                    tax_line = invoice_id.tax_line_ids[0]
                    tax_line.write({'amount': tax_line.amount + diff})
            else:
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos galutinė suma nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (amount_total_invoice, invoice_id.reporting_amount_total, data.get('row_number'))

        if body:
            raise exceptions.ValidationError(_(body))

        invoice_id.partner_data_force()
        invoice_id.with_context(skip_attachments=True).action_invoice_open()
        return invoice_id

    @api.model
    def create_move(self, invoice, rec):
        """
        Create artificial payment for account.invoice record created from etaksi.data.import
        Reconcile created account.move with the invoice
        :param invoice: account.invoice which the payment should be reconciled with
        :param rec: line that was read from the xls (dict)
        :return: None
        """

        data = []
        journals = self.env['account.journal'].search([('code', 'in', [PAYSERA_CODE, FOX_BOX_CODE])])
        paysera_sum = rec.get('paysera_sum') or 0
        if not tools.float_is_zero(paysera_sum, precision_digits=2):
            data.append((journals.filtered(lambda x: x.code == PAYSERA_CODE), paysera_sum))

        fox_box_sum = rec.get('fox_box_sum') or 0
        if not tools.float_is_zero(fox_box_sum, precision_digits=2):
            data.append((journals.filtered(lambda x: x.code == FOX_BOX_CODE), fox_box_sum))

        for journal, payment_amount in data:
            name = 'Mokėjimas ' + invoice.date_invoice
            move_lines = []
            credit_line = {
                'name': name,
                'date': invoice.date_invoice,
            }
            debit_line = credit_line.copy()
            if invoice.type == 'out_invoice':
                credit_line['credit'] = debit_line['debit'] = payment_amount
                credit_line['debit'] = debit_line['credit'] = 0.0
                credit_line['account_id'] = invoice.account_id.id
                debit_line['account_id'] = journal.default_debit_account_id.id
            else:
                credit_line['debit'] = debit_line['credit'] = payment_amount
                credit_line['credit'] = debit_line['debit'] = 0.0
                credit_line['account_id'] = invoice.account_id.id
                debit_line['account_id'] = journal.default_credit_account_id.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': journal.id,
                'date': invoice.date_invoice,
                'partner_id': invoice.partner_id.id,
            }
            move_id = self.sudo().env['account.move'].create(move_vals)
            move_id.post()
            if not tools.float_is_zero(invoice.residual, precision_digits=2):
                line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
                line_ids |= invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == invoice.account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()

    @api.model
    def unlink_move(self, invoice):
        """
        If corresponding invoice already exists in the system during XLS import
        and has related paysera/fox-box payments, we unlink them
        and later proceed with the creation of new payments
        :param invoice: account.invoice which the payment should be reconciled with
        :return: None
        """
        journals = self.env['account.journal'].search([('code', 'in', [PAYSERA_CODE, FOX_BOX_CODE])])
        move_lines = invoice.payment_move_line_ids.filtered(lambda x: x.journal_id.id in journals.ids)

        # We map lines to get move_id, because it contains more lines
        # Thus we unlink the parent object
        for move in move_lines.mapped('move_id'):
            move.mapped('line_ids').remove_move_reconcile()
            move.button_cancel()
            move.unlink()

    @api.model
    def re_arrange_data(self, data, invoice_numbers):
        """
        Re-organize data so every line with the same invoice number is interpreted as invoice lines
        of the same invoice
        :param data: invoice data
        :param invoice_numbers: unique invoice numbers
        :return: structured data, format  - [{}, {}...]
        """
        structured_data = []
        for number in invoice_numbers:
            invoice_data = [x for x in data if x.get('invoice_number') == number]
            invoice_lines = []
            amount_invoice_total = 0.0
            new_vals = {
                'invoice_lines': invoice_lines,
            }
            new_vals.update(invoice_data[0])
            for line in invoice_data:
                amount_line_total = line.get('amount_total')
                vals = {
                    'invoice_line_name': line.get('invoice_line_name'),
                    'product_name': line.get('product_name'),
                    'quantity': line.get('quantity'),
                    'price_unit': line.get('price_unit'),
                    'vat_rate': line.get('vat_rate'),
                    'analytic_code': line.get('analytic_code'),
                    'analytic_name': line.get('category'),
                    'amount_total': amount_line_total,
                }
                invoice_lines.append(vals)
                amount_invoice_total += amount_line_total

            # Round the final amount using odoo tools round
            # Python round rounds like this 9.075 -> 9.07
            # when it should be 9.075 -> 9.08
            amount_invoice_total = tools.float_round(amount_invoice_total, precision_digits=2)
            new_vals['amount_invoice_total'] = amount_invoice_total
            structured_data.append(new_vals)
        return structured_data

    @api.model
    def apply_invoice_differences(self, invoice, data):
        """
        If corresponding invoice already exists in the system during XLS import
        Check whether there are any changes between the system invoice and newly passed
        XLS data, if so, collect them and write them to account.invoice record
        :param invoice: found account.invoice
        :param data: XLS invoice data
        :return: None
        """
        # Collect the fields
        comment = data.get('comments')
        xls_invoice_lines = data.get('invoice_lines')

        partner = self.get_res_partner(data)
        user = self.get_res_user(data)
        journal = self.get_account_journal(data)

        # Declare change dicts
        new_invoice_vals = dict()
        invoice_lines_to_change = dict()
        re_confirm = False

        # Check for account_invoice changes
        if invoice.comment != comment:
            new_invoice_vals['comment'] = comment
        if user and invoice.user_id != user:
            new_invoice_vals['user_id'] = user.id
        if partner and invoice.partner_id != partner:
            new_invoice_vals['partner_id'] = partner.id
            re_confirm = True
        if journal and invoice.journal_id != journal:
            new_invoice_vals['journal_id'] = journal.id
            re_confirm = True

        # Check for account_invoice_line changes
        for xls_line in xls_invoice_lines:
            invoice_line = invoice.invoice_line_ids.filtered(
                lambda x: x.name == xls_line.get('invoice_line_name', str()))
            if invoice_line:
                # Get current product and tax
                product = self.get_product(xls_line)
                tax = self.get_account_tax(xls_line)
                analytic_account = self.get_analytic_account(xls_line)

                # Get current price/quantity
                price_unit = tools.float_round(xls_line.get('price_unit', 0), precision_digits=4)
                quantity = tools.float_round(xls_line.get('quantity', 0), precision_digits=3)

                new_line_vals = dict()
                if product and invoice_line.product_id != product:
                    new_line_vals['product_id'] = product.id

                # Invoice line will always have one tax_id
                if tax and tax not in invoice_line.invoice_line_tax_ids:
                    new_line_vals['invoice_line_tax_ids'] = [(6, 0, tax.ids)]

                if analytic_account and analytic_account != invoice_line.account_analytic_id:
                    new_line_vals['account_analytic_id'] = analytic_account.id

                if tools.float_compare(quantity, invoice_line.quantity, precision_digits=3) != 0:
                    new_line_vals['quantity'] = quantity

                if tools.float_compare(price_unit, invoice_line.price_unit, precision_digits=4) != 0:
                    new_line_vals['price_unit'] = price_unit

                if new_line_vals:
                    invoice_lines_to_change[invoice_line.id] = new_line_vals
                    re_confirm = True

        # Check for if there is any changes and push them if so.
        # Also check whether account_invoice record should be canceled and reconfirmed
        if new_invoice_vals or invoice_lines_to_change:
            re_confirm = True if invoice.state in ['open', 'paid'] and re_confirm else False
            new_partner = True if 'partner_id' in new_invoice_vals else False

            if re_confirm:
                journals = self.env['account.journal'].search([('code', 'in', [PAYSERA_CODE, FOX_BOX_CODE])])
                self.unlink_move(invoice)
                res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
                invoice.write(new_invoice_vals)
                if invoice_lines_to_change:
                    for line in invoice.invoice_line_ids:
                        line.write(invoice_lines_to_change.get(line.id, {}))

                if new_partner:
                    invoice.partner_data_force()
                invoice.action_invoice_open()

                # We only care about payments that are not from fox-box/paysera to be reassigned
                # since these two are going to be unlinked and recreated later anyways
                new_payment_dict = {
                    'expense_payment_lines': res.get('expense_payment_lines').filtered(
                        lambda x: x.journal_id not in journals),
                    'payment_lines': res.get('payment_lines').filtered(
                        lambda x: x.journal_id not in journals),
                    'gpm_payment_lines': res.get('gpm_payment_lines').filtered(
                        lambda x: x.journal_id not in journals),
                }
                invoice.action_re_assign_outstanding(
                    new_payment_dict, forced_partner=new_invoice_vals.get('partner_id'))
            else:
                invoice.write(new_invoice_vals)

    # Getters ---------------------------------------------------------------------------------------------------

    @api.model
    def get_res_partner(self, data):
        """
        Read partner info and search for/create res.partner
        :param data: Data dict representing one invoice from custom XLS
        :return: res.partner record
        """
        name = data.get('partner_name', False)
        code = data.get('partner_code', False)
        if code and name:
            partner_id = self.env['res.partner'].search([('kodas', '=', code)])
            if not partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': name,
                    'is_company': True,
                    'kodas': code,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')],
                        limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')],
                        limit=1).id,
                }
                partner_id = self.env['res.partner'].create(partner_vals)
                partner_id.vz_read()
            return partner_id
        else:
            raise exceptions.ValidationError(
                _('Nerasta partnerio informacija! | Eilutės nr: %s') % data.get('row_number'))

    @api.model
    def get_analytic_account(self, data):
        """
        Read invoice info and search for related account.analytic.account
        :param data: Data dict representing one invoice from custom XLS
        :return: account.analytic.account record
        """
        code = data.get('analytic_code')
        name = data.get('analytic_name')
        analytic_account = self.env['account.analytic.account']
        if code:
            analytic_account = self.env['account.analytic.account'].search([('code', '=', code)], limit=1)
        if not analytic_account and name:
            analytic_account = self.env['account.analytic.account'].search([('name', '=', name)], limit=1)
        return analytic_account

    @api.model
    def get_product(self, data):
        """
        Read invoice info and search for related product.product record
        :param data: Data dict representing one invoice from custom XLS
        :return: product.product record
        """
        product_name = data.get('product_name', False)
        product_id = self.env['product.product']
        if product_name:
            product_id = self.env['product.product'].search([('product_tmpl_id.name', '=', product_name)], limit=1)
        return product_id

    @api.model
    def get_account_tax(self, data):
        """
        Read invoice info and search for related account.tax record
        :param data: Data dict representing one invoice from custom XLS
        :return: account.tax record
        """
        vat_rate = data.get('vat_rate', 0)
        tax_id = self.env['account.tax'].search(
            [('amount', '=', vat_rate), ('type_tax_use', '=', 'sale'), ('price_include', '=', True)], limit=1)
        if not tax_id:
            raise exceptions.ValidationError(
                _('Neteisinga mokesčių informacija! | Eilutės nr: %s') % data.get('row_number'))
        return tax_id

    @api.model
    def get_res_user(self, data):
        """
        Read invoice info and search for res.users record that represents invoice manager
        :param data: Data dict representing one invoice from custom XLS
        :return: res.users record
        """
        manager_name = data.get('manager_name')
        user_id = self.env['res.users']
        if manager_name:
            user_id = self.env['res.users'].search([('name', '=', manager_name)], limit=1)
        return user_id if user_id else self.env.user

    @api.model
    def get_account_journal(self, data):
        """
        Read invoice info and search for account.journal record that corresponds to invoice numering
        :param data: Data dict representing one invoice from custom XLS
        :return: account.journal record
        """
        invoice_number = data.get('invoice_number')
        journal_code = invoice_number[:1]
        journal_id = self.env['account.journal'].search([('code', '=', journal_code), ('type', '=', 'sale')], limit=1)
        if not journal_id:
            raise exceptions.ValidationError(
                _('Klaida kuriant sąskaitą %s. Sąskaitos numeruotei nerastas žurnalas') % invoice_number)
        return journal_id


EtaksiDataImport()
