# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
import base64
import xlwt
import xlrd
from xlrd import XLRDError
import StringIO

FIELDS = [
    'product_name',
    'product_code',
    'category_name',
    'accounting_qty',
    'actual_qty',
    'uom'
]
REQUIRED_FIELDS = ['actual_qty']
FLOAT_FIELDS = ['actual_qty']
STRING_FIELDS = ['product_name', 'product_code', 'category_name', 'uom']


class StockInventoryImport(models.TransientModel):
    _name = 'stock.inventory.import'

    xls_data = fields.Binary(string='XLS file')
    xls_name = fields.Char(string='XLS file name', size=128)
    inventory_id = fields.Many2one('stock.inventory', string='Stock inventory', required=True, ondelete='cascade')

    @api.multi
    def import_inventory(self):
        """
        Method that imports inventory lines
        :return: None
        """
        self.ensure_one()
        if self.inventory_id.state not in ['draft', 'confirm']:
            raise exceptions.UserError(_('You cannot import in the current state'))
        header_values = self.get_table_header()
        if not self.xls_data:
            raise exceptions.UserError(_('File not provided.'))
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(self.xls_data))
        except XLRDError:
            raise exceptions.UserError(_('Wrong file format!'))

        sheet = wb.sheets()[0]
        recordset = []
        for row in range(sheet.nrows):
            if row < len(self.get_inventory_report_header()) + 1:
                continue
            col = 0
            record = {}
            for field in FIELDS:
                wrong_value = False
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = False

                if field in REQUIRED_FIELDS and not value and not isinstance(value, (int, float)):
                    raise exceptions.UserError(
                        _('Value not found for a required field: %s. Line - %s') % (
                            header_values[col], str(row + 1)))
                if field in STRING_FIELDS and value:
                    value, wrong_value = self.convert_to_string(value)
                if field in FLOAT_FIELDS and value:
                    value, wrong_value = self.convert_to_float(value)
                if wrong_value:
                    raise exceptions.UserError(_('Wrong value for field %s. Line - %s') % (
                        header_values[col], str(row + 1)))
                record[field] = value
                col += 1
            recordset.append(record)

        if not recordset:
            raise exceptions.UserError(_('No values to import'))

        self.fill_in_inventory(recordset)
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    @api.multi
    def export_inventory_template(self):
        """
        Method that exports XLS inventory template
        :return: XLS file download
        """
        self.ensure_one()
        header_values = self.get_table_header()
        inventory = self.inventory_id
        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet(_('Inventory'))
        xlwt.add_palette_colour('robo_background', 0x21)
        workbook.set_colour_RGB(0x21, 236, 240, 241)
        header_bold_brd = xlwt.easyxf('font: bold on; borders: left thin, right thin, bottom thick, top thin')
        header_bold_brd_clr = xlwt.easyxf('font: bold on; borders: left thin, right thin, bottom thin, top thin; '
                                          'pattern: pattern solid, fore_colour robo_background;')
        lines_editable = xlwt.easyxf('protection: cell_locked false;')
        inventory_report_header = self.get_inventory_report_header()
        row = 0
        for val in inventory_report_header:
            worksheet.write(row, 0, val, header_bold_brd_clr)
            row += 1
        col = 0
        for val in header_values:
            worksheet.write(row, col, val, header_bold_brd)
            width = 50 if not col else 20
            worksheet.col(col).width = 256 * width
            col += 1

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(len(inventory_report_header) + 1)
        worksheet.protect = True
        worksheet.password = 'robolabs_xls'

        for line in inventory.line_ids.sorted(lambda x: x.product_id.categ_id.name):
            row += 1
            worksheet.write(row, 0, line.product_id.name)
            worksheet.write(row, 1, line.product_id.default_code or str())
            worksheet.write(row, 2, line.product_id.categ_id.name)
            worksheet.write(row, 3, line.accounting_qty)
            worksheet.write(row, 4, '', lines_editable)
            worksheet.write(row, 5, line.product_uom_id.name)
            
        f = StringIO.StringIO()
        workbook.save(f)
        base64_file = f.getvalue().encode('base64')
        filename = _('Inventory %s.xls') % self.inventory_id.name
        attachement = self.env['ir.attachment'].create({
            'res_model': 'stock.inventory',
            'res_id': self.inventory_id.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=stock.inventory&res_id=%s&attach_id=%s' % (self.inventory_id.id,
                                                                                              attachement.id),
            'target': 'current',
        }

    @api.multi
    def fill_in_inventory(self, recordset):
        self.ensure_one()
        inventory = self.inventory_id
        sign = 1.0 if inventory.surplus else -1.0

        for record in recordset:
            product = self.find_product(record)
            if not product:
                raise exceptions.UserError(
                    _('Product %s was not found in the system.') % (record['product_code'] or record['product_name'])
                )
            corresponding_line = inventory.line_ids.filtered(
                lambda x, product_id=product.id: x.product_id.id == product_id
            )
            if len(corresponding_line) != 1:
                raise exceptions.UserError(
                    _('Corresponding line for product %s not found.') % (product.default_code or product.name)
                )
            actual_qty = record.get('actual_qty')
            consumed_qty = (corresponding_line.accounting_qty - actual_qty) * sign
            corresponding_line.write({
                'consumed_qty': consumed_qty
            })

    @api.multi
    def find_product(self, record):
        ProductProduct = self.env['product.product']
        ProductCategory = self.env['product.category']

        product = ProductProduct
        product_code = record.get('product_code')
        if product_code:
            product = ProductProduct.search([('default_code', '=', product_code)])
        product_name = record.get('product_name')
        if product_name:
            if len(product) > 1 or (not product and not product_code) or \
                    (product and product.with_context(lang='lt_LT').name != product_name and
                     product.with_context(lang='en_US').name != product_name):
                product = ProductProduct.with_context(lang='lt_LT').search([('name', '=', product_name)])
                if not product:
                    product = ProductProduct.with_context(lang='en_US').search([('name', '=', product_name)])
        if len(product) > 1:
            category = ProductCategory
            category_name = record.get('category_name')
            if category_name:
                category = ProductCategory.with_context(lang='lt_LT').search([('name', '=', category_name)],
                                                                             limit=1)
                if not category:
                    category = ProductCategory.with_context(lang='en_US').search([('name', '=', category_name)],
                                                                                 limit=1)
            if category:
                product = product.filtered(lambda x, category_id=category.id: x.categ_id.id == category_id)
            if len(product) != 1:
                raise exceptions.UserError(_('Product %s not found.') % product_code or product_name)
        return product

    @api.multi
    def get_inventory_report_header(self):
        self.ensure_one()
        inventory = self.inventory_id
        return [
            self.env.user.sudo().company_id.name,
            _('Inventory write-off: {}').format(inventory.name),
            _('Stock location: {}').format(inventory.location_id.name),
            _('Adjustment date: {}').format(inventory.date),
            _('Accounting date: {}').format(inventory.accounting_date),
            _('Write-off reason: {}').format(inventory.reason_line.name or str()),
        ]

    @api.model
    def get_table_header(self):
        return [
            _('Product name'),
            _('Product code'),
            _('Product category'),
            _('Accounting quantity'),
            _('Actual quantity'),
            _('Unit of measure')
        ]

    @api.model
    def convert_to_string(self, value):
        wrong_value = False
        try:
            value = str(value)
        except ValueError:
            wrong_value = True
        return value, wrong_value

    @api.model
    def convert_to_float(self, value):
        wrong_value = False
        try:
            value = float(value or 0.0)
        except ValueError:
            wrong_value = True
        return value, wrong_value

