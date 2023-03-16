# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from xlrd import XLRDError
import datetime

allowed_tax_calc_error = 0.05


class FrontDataImport(models.TransientModel):

    _name = 'front.data.import'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita')
    tax_id = fields.Many2one('account.tax', string='PVM')
    product_id = fields.Many2one('product.product', string='Produktas', required=True)
    action = fields.Selection([('draft', 'Netvirtinti'), ('open', 'Tvirtinti')], string='Ar tvirtinti importuotas sąskaitas?', default='draft', required=True)
    check_amounts = fields.Boolean(string='Tikrinti sumas', default=False)

    @api.multi
    def data_import(self):
        self.ensure_one()
        field_list = ['partner_code', 'partner_name', 'date', 'total_wo_vat', 'total_vat',
                      'total', 'account_analytic_id', 'account_code', 'currency_code']
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
            col = 0
            record = {'row_number': str(row + 1)}
            for field in field_list:
                try:
                    value = sheet.cell(row, col).value
                    if isinstance(value, tuple([float, int, long])):
                        value = tools.float_round(value, precision_digits=2)
                except IndexError:
                    value = False
                if field == 'date':
                    value = datetime.datetime(*xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                record[field] = value
                col += 1
            record_set.append(record)

        ids = []
        for record in record_set:
            self.validator(record)
            invoice = self.create_invoices(record)
            ids.append(invoice.id)

        domain = [('id', 'in', ids)]
        ctx = {
            'activeBoxDomain': "[('state','!=','cancel')]",
            'default_type': "out_invoice",
            'force_order': "recently_updated DESC NULLS LAST",
            'journal_type': "purchase",
            'lang': "lt_LT",
            'limitActive': 0,
            'params': {'action': self.env.ref('robo.open_client_invoice').id},
            'robo_create_new': self.env.ref('robo.new_client_invoice').id,
            'robo_menu_name': self.env.ref('robo.menu_pajamos').id,
            'robo_subtype': "pajamos",
            'robo_template': "RecentInvoices",
            'search_add_custom': False,
            'type': "in_invoice",
            'robo_header': {},
        }
        return {
            'context': ctx,
            'display_name': _('Pajamos'),
            'domain': domain,
            'name': _('Pajamos'),
            'res_model': 'account.invoice',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'header': self.env.ref('robo.robo_button_pajamos').id,
            'view_id': self.env.ref('robo.pajamos_tree').id,
            'view_mode': 'tree_expenses_robo,form,kanban',
            'views': [[self.env.ref('robo.pajamos_tree').id, 'tree_expenses_robo'],
                      [self.env.ref('robo.pajamos_form').id, 'form'],
                      [self.env.ref('robo.pajamos_kanban').id, 'kanban']],
            'with_settings': True,
        }

    def check_vat(self, data):
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
            tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('type_tax_use', '=', 'sale'),
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
        if code or name:
            partner_id = False
            if code:
                if not isinstance(code, tuple([str, unicode])):
                    code = str(code)
                    if '.' in code:
                        code = code.split('.')[0]
                partner_id = self.env['res.partner'].search([('kodas', '=', code)])
            if not partner_id and name:
                partner_id = self.env['res.partner'].search([('name', '=', name)])
            if not partner_id:
                if not name:
                    raise exceptions.Warning(
                        _('Nerasta partnerio informacija! | Eilutės nr: %s') % data.get('row_number'))
                if code:
                    country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                else:
                    country_id = self.env['res.country']
                try:
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
                except Exception as exc:
                    raise exceptions.Warning(
                        _('Nerasta partnerio informacija! | Eilutės nr: %s') % data.get('row_number'))
            return partner_id
        else:
            raise exceptions.Warning(_('Nerasta partnerio informacija! | Eilutės nr: %s') % data.get('row_number'))

    def get_account(self, data):
        code = data.get('account_code', False)
        account_id = self.env['account.account']
        if code:
            account_id = self.env['account.account'].search([('code', '=', code)])
        if not account_id:
            account_id = self.env['account.account'].search([('code', '=', '2410')])
        return account_id

    def get_analytic(self, data):
        code = data.get('account_analytic_id', False)
        analytic_id = self.env['account.account']
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
        total = data.get('total', False)
        if not total:
            body += _('Nerasta galutinė suma\n')
        total_wo_vat = data.get('total_wo_vat', False)
        if not total_wo_vat:
            body += _('Nerasta suma be PVM\n')
        total_vat = data.get('total_vat', False)
        if not total_vat:
            body += _('Nerasta PVM suma\n')
        if body:
            body += 'Sąskaitos kūrimo klaida | %s eilutė Excel faile |' % data.get('row_number')
            raise exceptions.Warning(body)

    def create_invoices(self, data):
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        default_location = self.env['stock.location'].search([('usage', '=', 'internal')], order='create_date desc', limit=1)
        invoice_type = 'out_invoice' if data.get('total') > 0 else 'out_refund'
        partner_id = self.get_partner(data)
        self.check_vat(data)
        invoice_obj = self.env['account.invoice'].sudo()
        account_obj = self.env['account.account'].sudo()
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        invoice_lines = []
        account_id = self.get_account(data)
        analytic_id = self.get_analytic(data)
        date = data.get('date')

        invoice_values = {
            'external_invoice': True,
            'account_id': account_id.id,
            'partner_id': partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'exc',
            'date_invoice': date,
            'imported_api': True,
        }
        currency = data.get('currency_code', False)
        if currency:
            invoice_values['currency_id'] = self.env['res.currency'].search([('name', '=', currency)]).id

        product_account = self.product_id.get_product_income_account(return_default=True)
        line_vals = {
            'product_id': self.product_id.id,
            'name': self.product_id.name,
            'quantity': 1,
            'price_unit': tools.float_round(data.get('total_wo_vat', 0), precision_digits=2),
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
        if self.check_amounts:
            if tools.float_compare(data.get('total_vat', 0.0), abs(invoice_id.amount_tax), precision_digits=2) != 0:
                line_diffs = False
                if tools.float_compare(
                        data.get('total_wo_vat', 0.0), abs(invoice_id.amount_untaxed), precision_digits=2):
                    line_diffs = True
                diff = tools.float_round(data.get('total_vat', False) - invoice_id.amount_tax, precision_digits=2)
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

            if tools.float_compare(data.get('total', 0.0), abs(invoice_id.reporting_amount_total), precision_digits=2):
                body += _('Klaida kuriant sąskaitą | Excel sąskaitos galutinė suma nesutampa su paskaičiuota suma '
                          '(%s != %s). | %s eilutė Excel faile \n') % \
                        (data.get('total', False), invoice_id.reporting_amount_total, data.get('row_number'))

        if body:
            raise exceptions.Warning(_(body))

        try:
            invoice_id.partner_data_force()
            if self.action == 'open':
                invoice_id.action_invoice_open()
        except Exception as e:
            raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos | '
                                       '%s eilutė Excel faile | Administratoriai informuoti') % (data.get('row_number'), e))

        if self.action == 'open':
            rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
            if rec and rec.state in ['installed', 'to upgrade']:
                wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                    {'location_id': default_location.id})
                wizard_id.create_delivery()
                if invoice_id.picking_id:
                    invoice_id.picking_id.action_assign()
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()

        # self.env.cr.commit()
        return invoice_id


FrontDataImport()
