# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from xlrd import XLRDError
from datetime import datetime

allowed_tax_calc_error = 0.05


class RivileImportWizard(models.TransientModel):

    _name = 'rivile.import.wizard'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita')
    tax_id = fields.Many2one('account.tax', string='PVM')
    product_id = fields.Many2one('product.product', string='Produktas', required=True)

    @api.multi
    def data_import(self):
        self.ensure_one()
        field_list = ['invoice_number', 'partner_code', 'partner_name', 'date', 'total_wo_vat', 'total_vat',
                      'total', 'is_paid', 'payment_account_code',
                      'account_code', 'account_analytic_id', 'credit_invoice']
        data = self.xls_data
        record_set = []
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(data))
        except XLRDError:
            raise exceptions.Warning(_('Netinkamas failo formatas!'))
        sheet = wb.sheets()[0]
        for row in range(sheet.nrows):
            if row == 0:
                continue
            record = {'row_number': str(row + 1)}
            for col, field in enumerate(field_list):
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = None
                if field == 'date' and value:
                    try:
                        value = datetime(*xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    except Exception as e:
                        pass
                if field == 'partner_code' and value:
                    try:
                        value = str(int(value))
                    except (UnicodeEncodeError, ValueError):
                        raise exceptions.UserError(
                            _('Netinkama partnerio kodo reikšmė: %s. Eilutė - %s.') % (
                                value, str(row + 1)))
                if field in ['total_wo_vat', 'total_vat', 'total'] and isinstance(value, basestring):
                    if value:
                        value = float(value)
                    else:
                        value = None
                record[field] = value
            record_set.append(record)

        ids = []
        for record in record_set:
            self.validator(record)
            invoice = self.create_invoices(record)
            ids.append(invoice.id)

        domain = [('id', 'in', ids)]
        purchase = self._context.get('purchase', False)
        ctx = {
            'activeBoxDomain': "[('state','!=','cancel')]",
            'default_type': "out_invoice",
            'force_order': "recently_updated DESC NULLS LAST",
            'journal_type': "sale",
            'lang': "lt_LT",
            'limitActive': 0,
            'params': {'action': self.env.ref('robo.open_client_invoice').id},
            'robo_create_new': self.env.ref('robo.new_client_invoice').id,
            'robo_menu_name': self.env.ref('robo.menu_pajamos').id,
            'robo_subtype': "pajamos",
            'robo_template': "RecentInvoices",
            'search_add_custom': False,
            'type': "out_invoice",
            'robo_header': {},
        }
        if purchase:
            ctx.update({
                'default_type': "in_invoice",
                'journal_type': "purchase",
                'params': {'action': self.env.ref('robo.robo_expenses_action').id},
                'robo_create_new': self.env.ref('robo.new_supplier_invoice').id,
                'robo_menu_name': self.env.ref('robo.menu_islaidos').id,
                'robo_subtype': 'expenses'
            })
            action = self.env.ref('robo.robo_expenses_action').read()[0]
            action.update({
                'ctx': ctx,
                'domain': domain,
            })
            return action
        else:
            action = self.env.ref('robo.open_client_invoice').read()[0]
            action.update({
                'ctx': ctx,
                'domain': domain,
            })
            return action

    def check_vat(self, data, purchase=False):
        amount = data.get('total')
        vat = data.get('total_vat')
        if amount and vat:
            try:
                amount = float(amount)
                vat = float(vat)
            except (ValueError, TypeError):
                raise exceptions.Warning(
                    _('Sąskaitos kūrimo klaida | %s eilutė Excel faile | Nepavyko nuskaityti sumos arba PVM duomenų')
                    % data.get('row_number'))
            sum_wo_vat = amount - vat
            percentage = round(((amount / sum_wo_vat) - 1) * 100, 0)
            tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('type_tax_use', '=', 'sale' if not purchase else 'purchase'),
                                                     ('price_include', '=', False)], limit=1)
            if self.tax_id:
                if tax_id.id != self.tax_id.id:
                    raise exceptions.Warning(_('Sąskaitos kūrimo klaida | '
                                               '%s eilutė Excel faile | Paduotas neteisingas PVM') % (
                                             data.get('row_number')))
            else:
                self.tax_id = tax_id
        if not self.tax_id:
            raise exceptions.Warning(_('%s eilutės PVM nustatymai neteisingi') % data.get('row_number'))

    def get_partner(self, data):
        name = data.get('partner_name', False)
        code = data.get('partner_code', False)
        if name:
            partner_id = self.env['res.partner'].search([('name', '=', name)])
            if not partner_id and code:
                partner_id = self.env['res.partner'].search([('kodas', '=', code)])
            if not partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': name,
                    'is_company': True if code else False,
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
            raise exceptions.Warning(_('Nerasta partnerio informacija! | Eilutės nr: %s') % data.get('row_number'))

    def get_account(self, data, purchase=False):
        code = data.get('account_code', False)
        if isinstance(code, (int, float)):
            try:
                code = str(int(code))
            except ValueError:
                pass
        account_id = self.env['account.account']
        if code:
            account_id = self.env['account.account'].search([('code', '=', code)])
        if not account_id:
            account_id = self.env['account.account'].search([('code', '=', '2410' if not purchase else '4430')])
        return account_id

    def get_analytic(self, data):
        code = data.get('account_analytic_id', False)
        analytic_id = self.env['account.analytic.account']
        if not self.account_analytic_id:
            if code:
                analytic_id = self.env['account.analytic.account'].search([('code', '=', code)])
        else:
            analytic_id = self.account_analytic_id
        return analytic_id

    def validator(self, data):
        body = str()
        date = data.get('date', False)
        if not date:
            body += _('Nerasta data\n')
        if date:
            try:
                date = data.get('date').replace('.', '-')
                datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except Exception as e:
                body += _('Nekorektiškas datos formatas!')
        total = data.get('total')
        if total is None:
            body += _('Nerasta galutinė suma\n')
        name = data.get('invoice_number', False)
        if not name:
            body += _('Nerastas saskaitos pavadinimas\n')
        total_wo_vat = data.get('total_wo_vat')
        if total_wo_vat is None:
            body += _('Nerasta suma be PVM\n')
        total_vat = data.get('total_vat')
        if total_vat is None:
            body += _('Nerasta PVM suma\n')
        is_paid = data.get('is_paid', False)
        if is_paid:
            if isinstance(is_paid, (int, float)):
                if is_paid not in [1, 0]:
                    body += _('Nekorektiškas apmokėjimo žymuo. Galimos reikšmės (True, False)\n')
            else:
                if not is_paid.lower() in ['true', 'false']:
                    body += _('Nekorektiškas apmokėjimo žymuo. Galimos reikšmės (True, False)\n')
        credit_invoice = data.get('credit_invoice', False)
        if credit_invoice:
            if isinstance(credit_invoice, (int, float)):
                if credit_invoice not in [1, 0]:
                    body += _('Nekorektiškas kreditinės sąskaitos žymuo. Galimos reikšmės (True, False)\n')
            else:
                if not credit_invoice.lower() in ['true', 'false']:
                    body += _('Nekorektiškas kreditinės sąskaitos žymuo. Galimos reikšmės (True, False)\n')
        if body:
            body += 'Sąskaitos kūrimo klaida | %s eilutė Excel faile |' % data.get('row_number')
            raise exceptions.Warning(body)

    def create_invoices(self, data):
        purchase = self._context.get('purchase', False)
        default_journal = self.env['account.journal'].search([('type', '=', 'sale' if not purchase else 'purchase')], limit=1)
        default_location = self.env['stock.location'].search([('usage', '=', 'internal')], order='create_date desc', limit=1)

        # sanitize is credit_invoice
        credit_invoice = data.get('credit_invoice', False)
        if credit_invoice:
            if isinstance(credit_invoice, (int, float)):
                credit_invoice = True if credit_invoice == 1 else False
            else:
                credit_invoice = True if credit_invoice.lower() in ['true'] else False
        if not purchase:
            invoice_type = 'out_refund' if credit_invoice else 'out_invoice'
        else:
            invoice_type = 'in_refund' if credit_invoice else 'in_invoice'
        partner_id = self.get_partner(data)
        self.check_vat(data, purchase=purchase)
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        invoice_lines = []
        account_id = self.get_account(data, purchase=purchase)
        analytic_id = self.get_analytic(data)
        date = data.get('date').replace('.', '-')

        invoice_values = {
            'external_invoice': True,
            'account_id': account_id.id,
            'partner_id': partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'exc',
            'number': data.get('invoice_number'),
            'move_name': data.get('invoice_number'),
            'date_invoice': date,
            'operacijos_data': date,
            'imported_api': True,
        }
        if purchase:
            invoice_values.update({
                'reference': data.get('invoice_number')
            })
            invoice_values.pop('number')
            invoice_values.pop('move_name')
        currency = data.get('currency_id', False)
        if currency:
            invoice_values['currency_id'] = self.env['res.currency'].search([('name', '=', currency)]).id

        if not purchase:
            product_account = self.product_id.get_product_income_account(return_default=True)
        else:
            product_account = self.product_id.get_product_expense_account(return_default=True)
        line_vals = {
            'product_id': self.product_id.id,
            'name': self.product_id.name,
            'quantity': 1,
            'price_unit': data.get('total_wo_vat'),
            'uom_id': self.product_id.product_tmpl_id.uom_id.id,
            'account_id': product_account.id,
            'invoice_line_tax_ids': [(6, 0, self.tax_id.ids)],
            'account_analytic_id': analytic_id.id,
        }
        invoice_lines.append((0, 0, line_vals))

        try:
            invoice_id = invoice_obj.create(invoice_values)
        except Exception as e:
            raise exceptions.Warning(_('Sąskaitos kūrimo klaida | '
                                       '%s eilutė Excel faile | Sąskaita su šiuo numeriu [%s] jau egzistuoja') % (data.get('row_number'), data.get('invoice_number')))

        body = str()
        if tools.float_compare(data.get('total_vat', 0.0), abs(invoice_id.amount_tax), precision_digits=2):
            line_diffs = False
            if tools.float_compare(data.get('total_wo_vat', 0.0), abs(invoice_id.amount_untaxed), precision_digits=2):
                line_diffs = True
            diff = tools.float_round(data.get('total_vat', 0.0) - invoice_id.amount_tax, precision_digits=2)
            if diff <= allowed_tax_calc_error:
                if line_diffs:
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
            else:
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos PVM suma nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (data.get('total', False), invoice_id.reporting_amount_total, data.get('row_number'))

        if tools.float_compare(data.get('total', False), abs(invoice_id.reporting_amount_total), precision_digits=2) != 0:
            body += _('Klaida kuriant sąskaitą | Excel sąskaitos galutinė suma nesutampa su paskaičiuota suma '
                      '(%s != %s). | %s eilutė Excel faile \n') % \
                    (data.get('total', False), invoice_id.reporting_amount_total, data.get('row_number'))

        if body:
            raise exceptions.Warning(_(body))

        # try:
        invoice_id.partner_data_force()
        invoice_id.with_context(skip_attachments=True).action_invoice_open()
        # except Exception as e:
        #     raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos | '
        #                                '%s eilutė Excel faile | Administratoriai informuoti') % (data.get('row_number'), e))

        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
        if rec and rec.state in ['installed', 'to upgrade']:
            wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                {'location_id': default_location.id})
            wizard_id.create_delivery()
            if invoice_id.picking_id:
                invoice_id.picking_id.action_assign()
                if invoice_id.picking_id.state == 'assigned':
                    invoice_id.picking_id.do_transfer()

        # sanitize is paid
        is_paid = data.get('is_paid', False)
        if is_paid:
            if isinstance(is_paid, (int, float)):
                is_paid = True if is_paid == 1 else False
            else:
                is_paid = True if is_paid.lower() in ['true'] else False
        if is_paid and purchase:
            raise exceptions.UserError(_('Negalima nurodyti apmokėjimo pirkimų sąskaitoms.'))
        if is_paid and not purchase:
            payment_account = data.get('payment_account_code', '2721')
            if isinstance(payment_account, (int, float)):
                try:
                    payment_account = str(int(payment_account))
                except ValueError:
                    pass
            account_id = self.env['account.account'].search([('code', '=', payment_account)])
            if not account_id:
                account_id = self.env['account.account'].search([('code', '=', '2721')])
            name = 'Mokėjimas ' + invoice_id.number if invoice_id.number else invoice_id.date_invoice
            move_lines = []

            credit_line = {
                'name': name,
                'date': invoice_id.date_invoice,
            }
            if invoice_id.type == 'out_invoice':
                credit_line['credit'] = invoice_id.amount_total
                credit_line['debit'] = 0.0
                credit_line['account_id'] = invoice_id.account_id.id
            else:
                credit_line['debit'] = invoice_id.amount_total
                credit_line['credit'] = 0.0
                credit_line['account_id'] = invoice_id.account_id.id

            debit_line = {
                'name': name,
                'date': invoice_id.date_invoice,
            }
            if invoice_id.type == 'out_invoice':
                debit_line['debit'] = invoice_id.amount_total
                debit_line['credit'] = 0.0
                debit_line['account_id'] = account_id.id
            else:
                debit_line['credit'] = invoice_id.amount_total
                debit_line['debit'] = 0.0
                debit_line['account_id'] = account_id.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': default_journal.id,
                'date': invoice_id.date_invoice,
                'partner_id': invoice_id.partner_id.id,
            }
            move_id = self.env['account.move'].sudo().create(move_vals)
            move_id.post()
            line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice_id.account_id.id)
            if len(line_ids) > 1:
                line_ids = line_ids.filtered(lambda x: x.credit)
            line_ids |= invoice_id.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice_id.account_id.id)
            if len(line_ids) > 1:
                line_ids.with_context(reconcile_v2=True).reconcile()
        return invoice_id


RivileImportWizard()
