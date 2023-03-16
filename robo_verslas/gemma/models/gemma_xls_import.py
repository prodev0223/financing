# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
import base64
import xlrd
from odoo.api import Environment
import threading
import odoo
from xlrd import XLRDError
from dateutil.relativedelta import relativedelta
from datetime import datetime
import logging
import xlwt
import StringIO

_logger = logging.getLogger(__name__)

date_mapper = {
    'Sausis': '2019-01-01',
    'Vasaris': '2019-02-01',
    'Kovas': '2019-03-01',
    'Balandis': '2019-04-01',
    'Gegužė': '2019-05-01',
    'Birželis': '2019-06-01',
    'Liepa': '2019-07-01',
    'Rugpjūtis': '2019-08-01',
    'Rugsėjis': '2019-09-01',
    'Spalis': '2019-10-01',
    'Lapkritis': '2019-11-01',
    'Gruodis': '2019-12-01',
    }

vat_mapper = {
    'PVM1': '0',
    'PVM3': '1',
    'PVM12': '2',
    'PVM5': '3',
    'PVM25': '4',
    'PVM9': '5',
}


def check_multiple_white_spaces(text):
    if '  ' in text:
        return text.replace('  ', ' ')
    return text


class GemmaXlsWizard(models.TransientModel):

    _name = 'gemma.xls.wizard'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)

    tax_id = fields.Many2one('account.tax', string='PVM', default=lambda self: self.env['account.tax'].search(
                                      [('code', '=', 'PVM5'),
                                       ('type_tax_use', '=', 'sale'),
                                       ('price_include', '=', True)], limit=1), required=True)
    product_id = fields.Many2one('product.product', string='Produktas', required=True,
                                 default=lambda self: self.env['product.product'].search([('default_code', '=', 'GPX')]))

    only_gp_sales = fields.Boolean(string='Traukti tik GP produktus', default=True)

    @api.multi
    def data_import(self):
        self.ensure_one()
        field_list = ['partner_name', 'debt_sum', 'month_date']
        data = self.xls_data
        record_set = []
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(data))
        except XLRDError:
            raise exceptions.Warning(_('Netinkamas failo formatas!'))
        sheet = wb.sheets()[0]

        bug_report = str()
        for row in range(sheet.nrows):
            col = 0
            record = {'row_number': str(row + 1)}
            for field in field_list:
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = False
                if isinstance(value, tuple([str, unicode])):
                    value = value.strip()
                record[field] = value
                col += 1

            partner_value = record.get('partner_name', False)
            if not partner_value:
                continue

            if partner_value:
                partner_value = check_multiple_white_spaces(partner_value)
                partner_id = self.env['res.partner'].search([('name', '=ilike', partner_value)])
                if not partner_id and ' ' in partner_value:
                    partner_value_list = partner_value.split(' ')
                    partner_value = ' '.join(partner_value_list[1:]) + ' ' + partner_value_list[0]
                    partner_id = self.env['res.partner'].search([('name', '=ilike', partner_value)])
                if not partner_id:
                    bug_report += 'Nerastas Partneris %s\n' % partner_value
                elif partner_id and len(partner_id) > 1:
                    bug_report += 'Partnerių duplikatai %s %s\n' % (partner_id[0].name, partner_id[1].name)
                else:
                    record['partner_id'] = partner_id.id
            month_value = record.get('month_date', False)
            if not month_value:
                bug_report += 'Nėpaduotas mėnuo. Eilutė %s\n' % record.get('row_number')
            if month_value:
                try:
                    date_mapper.get(month_value)
                except KeyError:
                    bug_report += 'Blogas datos formatas. Eilutė %s\n' % record.get('row_number')
            try:
                float(record.get('debt_sum', 0) or 0)
            except ValueError:
                bug_report += 'Neteisinga XLS suma. Eilutė %s\n' % record.get('row_number')

            record_set.append(record)

        if bug_report:
            raise exceptions.Warning(_(bug_report))

        if self._context.get('xls_check'):
            diffs = []
            for record in record_set:

                debt_factual = float(record.get('debt_sum', False) or 0)
                month_value = record.get('month_date', False)
                if not record.get('partner_id', False):
                    continue
                partner_id = self.env['res.partner'].browse(record.get('partner_id'))

                date_from = date_mapper.get(str(month_value))
                date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = date_from_dt + relativedelta(day=31)
                date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                gsl = self.env['gemma.sale.line'].search([('partner_id', '=', partner_id.id),
                                                          ('state', 'in', ['created'])])

                date_to_ch = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from_ch = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)

                gsl = gsl.filtered(lambda x: date_to_ch >= datetime.strptime(x.sale_day, tools.DEFAULT_SERVER_DATE_FORMAT) >= date_from_ch)
                if self.only_gp_sales:
                    gsl = gsl.filtered(lambda x: x.is_gp)
                debt_current = sum(x for x in gsl.mapped('price'))

                diff = tools.float_round(debt_factual - debt_current, precision_digits=2)
                if not tools.float_is_zero(diff, precision_digits=2):
                    diffs.append({
                        'partner_name': partner_id.display_name,
                        'debt': diff
                    })

            wb = xlwt.Workbook()
            ws = wb.add_sheet('Skolu ataskaita')
            ws.write(0, 0, 'Partneris')
            ws.write(0, 1, 'Skola')
            index = 1
            for row in diffs:
                ws.write(index, 0, row['partner_name'])
                ws.write(index, 1, float(row['debt']))
                index += 1
            f = StringIO.StringIO()
            wb.save(f)
            base64_file = f.getvalue().encode('base64')
            attach_id = self.env['ir.attachment'].create({
                'res_model': 'gemma.xls.wizard',
                'res_id': self[0].id,
                'type': 'binary',
                'name': 'Skolų ataskaita.xls',
                'datas_fname': 'Skolų ataskaita.xls',
                'datas': base64_file
            })
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/binary/download?res_model=gemma.xls.wizard&res_id=%s&attach_id=%s' % (
                    self[0].id, attach_id.id),
                'target': 'self',
            }
        else:
            threaded_calculation = threading.Thread(target=self.create_invoices_thread, args=(record_set,
                                                                                              self.product_id.id,
                                                                                              self.tax_id.id))
        threaded_calculation.start()

    @api.multi
    def create_invoices_thread(self, record_set, product_id, tax_id):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            product_id = env['product.product'].browse(product_id)
            tax_id = env['account.tax'].browse(tax_id)
            index = 1
            for record in record_set:
                if index % 10 == 0:
                    _logger.info("Import: %s/%s" % (index, len(record_set)))
                index += 1
                # create invoices

                debt_factual = float(record.get('debt_sum', False) or 0)
                month_value = record.get('month_date', False)
                if not record.get('partner_id', False):
                    continue
                partner_id = env['res.partner'].browse(record.get('partner_id'))
                account_id = env['account.account'].search([('code', '=', '2410')])

                date_from = date_mapper.get(str(month_value))
                date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = date_from_dt + relativedelta(day=31)
                date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                # product_skip = ['ADM', 'ADMIN', 'KORT1'] todo leave for now
                gsl = env['gemma.sale.line'].search([('partner_id', '=', partner_id.id),
                                                     ('state', 'in', ['created'])])

                date_to_ch = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from_ch = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)

                gsl = gsl.filtered(lambda x: date_to_ch >= datetime.strptime(x.sale_day, tools.DEFAULT_SERVER_DATE_FORMAT) >= date_from_ch)
                if self.only_gp_sales:
                    gsl = gsl.filtered(lambda x: x.is_gp)
                debt_current = sum(x for x in gsl.mapped('price'))
                diff = tools.float_round(debt_factual - debt_current, precision_digits=2)
                if not tools.float_is_zero(diff, precision_digits=2):
                    continue
                values = {
                    'ext_product_code': product_id.default_code,
                    'partner_id': partner_id.id,
                    'qty': 1.0,
                    'price': diff,
                    'receipt_total': diff,
                    'sale_date': date_from,
                    'bed_day_date': date_from,
                    'vat_code': vat_mapper.get(tax_id.code, False),
                }
                sale_id = env['gemma.sale.line'].sudo().create(values)

                if diff < 0:
                    diff = abs(diff)
                    invoice_type = 'out_refund'
                else:
                    invoice_type = 'out_invoice'

                default_journal = env['account.journal'].search([('type', '=', 'sale')], limit=1)
                default_location = env['stock.location'].search([('usage', '=', 'internal')],
                                                                     order='create_date desc', limit=1)

                invoice_obj = env['account.invoice'].sudo()
                account_obj = env['account.account'].sudo()
                delivery_wizard = env['invoice.delivery.wizard'].sudo()
                invoice_lines = []

                invoice_values = {
                    'external_invoice': True,
                    'account_id': account_id.id,
                    'partner_id': partner_id.id,
                    'journal_id': default_journal.id,
                    'invoice_line_ids': invoice_lines,
                    'type': invoice_type,
                    'price_include_selection': 'inc',
                    'date_invoice': date_from,
                    'imported_api': True,
                }
                product_account = product_id.get_product_income_account(return_default=True)
                line_vals = {
                    'product_id': product_id.id,
                    'name': product_id.name,
                    'quantity': 1,
                    'price_unit': diff,
                    'uom_id': product_id.product_tmpl_id.uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                    'gemma_sale_line_ids': [(6, 0, sale_id.ids)],
                }
                invoice_lines.append((0, 0, line_vals))

                try:
                    invoice_id = invoice_obj.create(invoice_values)
                    sale_id.write({'state': 'created'})
                except Exception as e:
                    _logger.info('Klaida kuriant sąskaitą partneriui %s. Pranešimas %s \n' % (record.get('partner_name'), e))
                    continue

                try:
                    invoice_id.partner_data_force()
                    invoice_id.action_invoice_open()
                except Exception as e:
                    _logger.info('Klaida tvirtinant sąskaitą partneriui %s. Pranešimas %s \n' % (record.get('partner_name'), e))
                    continue

                rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
                if rec and rec.state in ['installed', 'to upgrade']:
                    wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                        {'location_id': default_location.id})
                    wizard_id.create_delivery()
                    if invoice_id.picking_id:
                        invoice_id.picking_id.action_assign()
                        if invoice_id.picking_id.state == 'assigned':
                            invoice_id.picking_id.do_transfer()

                if partner_id.gemma_lock_date:
                    lock_date_dt = datetime.strptime(partner_id.gemma_lock_date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if lock_date_dt < date_to_dt:
                        partner_id.write({'gemma_lock_date': date_to})
                else:
                    partner_id.write({'gemma_lock_date': date_to})
                new_cr.commit()
            _logger.info('Import Finished')
            new_cr.close()


GemmaXlsWizard()
