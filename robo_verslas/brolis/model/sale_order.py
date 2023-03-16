# -*- coding: utf-8 -*-
import os
from sys import platform
import cStringIO as StringIO
import xlrd
import xlwt

from xlutils.filter import process, XLRDReader, XLWTWriter

from odoo import models, api

BUYER_ROW = 6
SALESMAN_ROW = 10
FIRST_SOL_ROW = 17

def copy2(wb):
    w = XLWTWriter()
    process(XLRDReader(wb, 'unknown.xlsx'), w)
    return w.output[0][1], w.style_list

SO_LINE_DESC_STYLE = xlwt.easyxf('align: wrap on, vert center; borders: left thin, right thin, top thin, bottom thin; '
                                 'pattern: pattern solid, fore_color white;')
SO_LINE_QTY_STYLE = xlwt.easyxf('align: vert center, horiz center; borders: left thin, right thin, top thin, bottom thin;'
                                ' pattern: pattern solid, fore_color white;')

class SOExcelSheet:
    def __init__(self):
        self.wb = None
        self.template = None
        self.wstyle = None
        self.load_template()
        self.ws = self.wb.get_sheet(0)
        self.nb_so_line = 0

    def load_template(self):
        if platform == 'win32':
            xls_flocation = '\\data\\product_order_template.xls'
        else:
            xls_flocation = '/data/product_order_template.xls'
        if platform == 'win32':
            img_flocation = '\\data\\brolis_logo.bmp'
        else:
            img_flocation = '/data/brolis_logo.bmp'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        img_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + img_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        self.template = rb
        self.wb, self.wstyle = copy2(rb)
        self.wb.get_sheet(0).insert_bitmap(img_loc, 1, 1)

    def add_order_number(self, number):
        self.ws.write(2, 2, u'Nr. ' + number, style=xlwt.easyxf("font: bold on, height 220; align: horiz right"))

    def add_buyer(self, vals):
        self.ws.write(BUYER_ROW, 2, vals.get('name'))
        self.ws.write(BUYER_ROW + 1, 2, vals.get('address'))

    def add_salesman(self, vals):
        self.ws.write(SALESMAN_ROW, 2, vals.get('name', ''))
        self.ws.write(SALESMAN_ROW + 1, 2, vals.get('email', ''))
        self.ws.write(SALESMAN_ROW + 2, 2, vals.get('phone', ''))

    def add_so_line(self, desc, qty):
        # Row heigh is approximated by description lines + extra lines for long lines. To be sure, we add 1 more
        desc_lines = len(desc.split('\n'))
        extra_lines = sum(len(line)//50 for line in desc.split('\n'))  # Cell length is approximately 50 chars
        self.ws.row(FIRST_SOL_ROW + self.nb_so_line).height_mismatch = True
        self.ws.row(FIRST_SOL_ROW + self.nb_so_line).height = 256 * (desc_lines + extra_lines + 1)
        self.ws.write_merge(FIRST_SOL_ROW + self.nb_so_line,FIRST_SOL_ROW + self.nb_so_line, 1, 2, desc, style=SO_LINE_DESC_STYLE)
        self.ws.write(FIRST_SOL_ROW + self.nb_so_line, 3, qty, style=SO_LINE_QTY_STYLE)
        self.nb_so_line += 1

    def write_footer(self):
        bold_font = xlwt.easyxf("font: bold on")
        italic_font = xlwt.easyxf("font: italic on; borders: top thin; pattern: pattern solid, fore_color white;")
        footer_lines = (u'Dengiamos pusės:', u'Dengiamas plotas, m2:', u'Kiekis, m:', u'Pagaminimo terminas:')
        start_row = FIRST_SOL_ROW + self.nb_so_line + 3
        for index, text in enumerate(footer_lines, start_row):
            self.ws.write(index, 1, text, style=bold_font)
            self.ws.write(index, 2, '.......')

        start_row += len(footer_lines) + 1
        footer_lines = (u'! Gamybos užsakymas patvirtinamas pervedant 50 proc. avansą.',)
        for index, text in enumerate(footer_lines, start_row):
            self.ws.write(index, 1, text, style=bold_font)

        start_row += len(footer_lines)
        footer_lines = (u'Negavus avanso per 2 d.d. po užsakymo pasirašymo,',
                        u'užsakymas laikomas nepatvirtintu.')
        for index, text in enumerate(footer_lines, start_row):
            self.ws.write(index, 1, text)

        start_row += len(footer_lines) + 1
        self.ws.write(start_row, 1, u'Pardavėjas', style=bold_font)
        self.ws.write(start_row, 2, u'Pirkėjas', style=bold_font)

        start_row += 2
        self.ws.write(start_row, 1, u'Vardas, pavardė, parašas', style=italic_font)
        self.ws.write_merge(start_row, start_row, 2, 3, u'Vardas, pavardė, parašas', style=italic_font)


SOExcelSheet()


class SaleOrder(models.Model):
    _inherit = 'sale.order'


    @api.multi
    def _get_salesman_info(self):
        self.ensure_one()
        res = {}
        if self.user_id:
            employee = self.user_id.sudo().employee_ids[0] if self.user_id.sudo().employee_ids else None
            if employee:
                res = {'name': employee.name,
                        'email': employee.work_email,
                        'phone': employee.work_phone}
            else:
                res = {'name': self.user_id.sudo().name}
        return res

    @api.multi
    def export_sale_order_excel(self):
        self.ensure_one()
        xls = SOExcelSheet()
        xls.add_order_number(self.name)
        xls.add_buyer({'name': self.partner_id.name,
                       'address': self.partner_id.with_context(skip_name=True).contact_address_line})
        xls.add_salesman(self._get_salesman_info()) #todo
        for line in self.order_line:
            xls.add_so_line(desc=line.name, qty=str(line.secondary_uom_qty) + ' ' + line.secondary_uom_id.name)
        xls.write_footer()
        f = StringIO.StringIO()
        xls.wb.save(f)
        base64_file = f.getvalue().encode('base64')
        filename = 'Gamybos užsakymas Nr %s.xls' % self.name
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'sale.order',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=sale.order&res_id=%s&attach_id=%s' % (self.id,attach_id.id),
            'target': 'current',
        }

    @api.multi
    def action_invoice_create(self, grouped=False, final=False):
        if not self.env.user.has_group('base.group_system'):
            self.check_access_rights('write')
            self.check_access_rule('write')
            self.env['account.invoice'].check_access_rights('create')
            for rec in self:
                rec.message_post('Creating invoice')
        invoice_ids = super(SaleOrder, self.sudo()).action_invoice_create(grouped, final)
        for invoice in self.env['account.invoice'].browse(invoice_ids):
            invoice.message_post('Created from sale order')
        return invoice_ids


SaleOrder()