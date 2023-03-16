# -*- coding: utf-8 -*-
import base64
from datetime import datetime
import xlrd
from xlrd import XLRDError
from odoo import _, exceptions, tools
from six import iteritems

FIELD_MAPPING = {
    'grouping': 'Važtaraščio identifikatorius',
    'src_location_code': 'Prekių pakrovimo sandėlio kodas',
    'dst_location_code': 'Prekių pristatymo sandėlio kodas',
    'date': 'Suplanuota data',
    'confirm': 'Patvirtinti',
    'transfer': 'Perduoti prekes',
    'product_code': 'Produkto kodas',
    'product_name': 'Produkto pavadinimas',
    'product_qty': 'Produkto kiekis',
}

FIELDS = ['grouping', 'src_location_code', 'dst_location_code', 'date', 'confirm', 'transfer', 'product_code',
          'product_name', 'product_qty']
REQUIRED_FIELDS = ['grouping', 'src_location_code', 'dst_location_code', 'date', 'product_qty']
STRING_FIELDS = ['grouping', 'src_location_code', 'dst_location_code', 'confirm', 'transfer', 'product_code',
                 'product_name']
DATE_FIELDS = ['date']
FLOAT_FIELDS = ['product_qty']
BOOLEAN_FIELDS = ['confirm', 'transfer']


def import_pickings(self, import_file):
    """
    Create pickings from values specified in the import file
    :param self: Environment variable
    :param import_file: File to import from
    :return: None
    """
    env = self.sudo().env
    StockPicking = env['stock.picking']
    recordset = parse_import_file(import_file)
    record_values = parse_record_values(env, recordset)

    for key, value in iteritems(record_values):
        confirm = value.get('confirm')
        transfer = value.get('transfer')
        picking_values = value.get('header')
        picking = StockPicking.create(picking_values)
        if confirm or transfer:
            picking.action_confirm()
        if transfer:
            picking.action_assign()
            if picking.state == 'assigned':
                picking.do_transfer()


def parse_import_file(import_file):
    """
    Parse the import file validating all the required fields
    :param import_file: File that is imported
    :return: List of parsed values
    """
    try:
        wb = xlrd.open_workbook(file_contents=base64.decodestring(import_file))
    except XLRDError:
        raise exceptions.UserError(_('Wrong file format!'))

    recordset = []
    errors = str()
    sheet = wb.sheets()[0]
    for row in range(sheet.nrows):
        if row == 0:
            continue
        col = 0
        record = {'row_number': str(row + 1)}
        record_required_fields = list(REQUIRED_FIELDS)
        for field in FIELDS:
            wrong_value = False
            try:
                value = sheet.cell(row, col).value
            except IndexError:
                value = False

            if field in DATE_FIELDS and value:
                value, wrong_value = convert_to_date(value, wb.datemode)
            elif field in STRING_FIELDS and value:
                value, wrong_value = convert_to_string(value)
                if not wrong_value and field in BOOLEAN_FIELDS:
                    value = value.lower() == 'taip'
            elif field in FLOAT_FIELDS and value:
                value, wrong_value = convert_to_float(value)

            if wrong_value:
                errors += _('Wrong value for field %s. Line - %s') % (FIELD_MAPPING[field], str(row + 1)) + '\n'

            # Update the required fields for the record based on product code
            if field == 'product_code' and not value:
                record_required_fields.append('product_name')

            # General required field checks
            if field in record_required_fields and not value:
                errors += _('Value not found for a required field: %s. Line - %s') % \
                          (FIELD_MAPPING[col], str(row + 1)) + '\n'
            record[field] = value
            col += 1
        recordset.append(record)
    if errors:
        raise exceptions.UserError(errors)
    return recordset


def parse_record_values(env, parsed_values):
    """
    Parse values form the file into records to create
    :param env: Environment variable
    :param parsed_values: Values parsed from file
    :return: Values for records to create
    """
    StockLocation = env['stock.location'].sudo()
    Product = env['product.product'].sudo()
    # {GROUPING KEY: {CONFIRM: True/False, TRANSFER: True/False, HEADER: { MOVE_LINES: [{},{},..] } } }
    grouped_records = dict()
    errors = str()

    for record in parsed_values:
        row = record.get('row_number')
        source_location_code = record.get('src_location_code')
        destination_location_code = record.get('dst_location_code')
        key = '{}/{}/{}'.format(record.get('grouping'), source_location_code, destination_location_code)
        parse_picking_header = key not in grouped_records
        grouped_records.setdefault(key, dict())
        if parse_picking_header:
            src_location = StockLocation.search([('usage', '=', 'internal'),
                                                 ('warehouse_id.code', '=', source_location_code)], limit=1)
            if not src_location:
                errors += _('Warehouse %s not found. Line - %s') % (source_location_code, row) + '\n'

            picking_type = src_location.warehouse_id.int_type_id
            dst_location = StockLocation.search([('usage', '=', 'internal'),
                                                 ('warehouse_id.code', '=', destination_location_code)], limit=1)
            if not dst_location:
                errors += _('Warehouse %s not found. Line - %s') % (destination_location_code, row) + '\n'

            header_values = {
                'picking_type_id': picking_type.id,
                'date': record.get('date'),
                'location_id': src_location.id,
                'location_dest_id': dst_location.id
            }

            grouped_records[key].update({
                'header': header_values,
                'confirm': record.get('confirm'),
                'transfer': record.get('transfer')
            })
        header = grouped_records[key].get('header')
        header.setdefault('move_lines', list())
        product = Product
        product_code = record.get('product_code')
        if product_code:
            product = Product.search([('default_code', '=', product_code)])
        product_name = record.get('product_name')
        if product_name:
            if len(product) > 1 or not product:
                product = Product.with_context(lang='lt_LT').search([('name', '=', product_name)])
            if not product:
                product = Product.with_context(lang='en_US').search([('name', '=', product_name)])
        if not product:
            errors += _('Product %s not found. Line - %s') % (product_code or product_name, row) + '\n'
        if len(product) > 1:
            errors += _('Multiple occurrences of product %s found.') % \
                      (product_code or product_name, row) + '\n'
        move_values = {
            'product_id': product.id,
            'name': product.name,
            'product_uom': product.uom_id.id,
            'date': header.get('date'),
            'date_expected': header.get('date'),
            'location_id': header.get('location_id'),
            'location_dest_id': header.get('location_dest_id'),
            'product_uom_qty': record.get('product_qty')
        }
        header['move_lines'].append((0, 0, move_values))
    if errors:
        raise exceptions.UserError(errors)
    return grouped_records


def convert_to_string(value):
    wrong_value = False
    if isinstance(value, tuple([str, unicode])):
        return value, wrong_value
    try:
        value = str(int(value))
    except ValueError:
        try:
            value = str(value)
        except ValueError:
            wrong_value = True
    return value, wrong_value


def convert_to_float(value):
    wrong_value = False
    try:
        value = float(value or 0.0)
    except ValueError:
        wrong_value = True
    return value, wrong_value


def convert_to_date(value, date_mode):
    wrong_value = False
    try:
        value = datetime(*xlrd.xldate_as_tuple(value, date_mode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    except ValueError:
        wrong_value = True
    return value, wrong_value

