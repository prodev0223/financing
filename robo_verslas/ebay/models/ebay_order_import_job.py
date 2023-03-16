# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _
from odoo.addons.queue_job.job import job
from dateutil.parser import parse
from .. import ebay_tools as et
from datetime import datetime
import StringIO
import base64
import csv
import re


def parse_numeric_value(value, num_regex=None):
    """
    Parses numeric value from eBay CSV. Amount fields
    are passed in this format - 'AU $41.56', thus we
    strip all the non number characters and convert the value
    :return: float: converted value
    """
    # Search for first number in the value, and
    # strip the string to only leave the number
    if num_regex is None:
        num_regex = re.search(r"\d", value)

    numeral_part = 0.0
    if num_regex:
        numeral_part = value[num_regex.start():]
        try:
            numeral_part = float(numeral_part)
        except (TypeError, ValueError):
            raise exceptions.ValidationError(_('Incorrect numeric value %s!') % numeral_part)
    return numeral_part


def parse_numeric_value_currency(value):
    """
    Parses numeric value from eBay CSV. Amount fields
    are passed in this format - 'AU $41.56'.
    Method parses both, custom currency identifier
    and numeric value.
    :return: float: converted value, str: custom currency code
    """
    # Search for first number in the value, and
    # strip the string to only leave the number
    num_regex = re.search(r"\d", value)
    numeral_part = currency_code = None
    if num_regex:
        numeral_part = parse_numeric_value(value, num_regex)
        currency_code = value[:num_regex.start()]
    return numeral_part, currency_code


class EbayOrderImportJob(models.Model):
    """
    Model that holds information about failed/imported Ebay tasks
    """
    _name = 'ebay.order.import.job'

    file_data = fields.Binary(string='File data')
    file_name = fields.Char(string='File name')
    origin_country_id = fields.Many2one('res.country')
    execution_start_date = fields.Datetime(string='Execution date start')
    execution_end_date = fields.Datetime(string='Execution date end')
    execution_state = fields.Selection([
        ('in_progress', 'In progress'),
        ('finished', 'Processed successfully'),
        ('failed', 'Server error'),
        ('warning', 'Data error')],
        string='Execution state', default='in_progress',
    )
    execution_errors = fields.Text(string='Import errors')

    created_order_ids = fields.Many2many('ebay.order')
    show_created_record_button = fields.Boolean(
        compute='_compute_show_corrected_record_button',
    )

    @api.multi
    def _compute_show_corrected_record_button(self):
        """Check whether corrected record opening button should be shown"""
        for rec in self:
            rec.show_created_record_button = rec.execution_state != 'in_progress' and rec.created_order_ids

    @api.multi
    def action_open_orders(self):
        """
        Open invoice tree with domain filtering the invoices that
        were created by this data import job
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('ebay.action_open_ebay_order').read()[0]
        action['domain'] = [('id', 'in', self.created_order_ids.ids)]
        return action

    @api.multi
    def button_reset_job_state(self):
        """
        Method that is used to reset stuck job state
        :return: None
        """
        self.write({'execution_state': 'warning'})

    @job
    @api.multi
    def preprocess_import_job(self, update_present_data):
        """
        Call import job processing by wrapping everything
        in try except block to catch non-data errors
        :return: None
        """
        self.ensure_one()
        try:
            self.process_import_job(update_present_data)
        except Exception as exc:
            self.write({
                'execution_state': 'failed',
                'execution_errors': exc.args,
                'execution_end_date': datetime.utcnow().strftime
                (tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })

    @api.multi
    def process_import_job(self, update_present_data):
        """Processes import job that is not in finished state"""
        self.ensure_one()
        if self.execution_state == 'finished':
            return

        # Define main object and set for created orders
        EbayOrder = created_orders = self.env['ebay.order']

        raw_orders_data = []
        structured_orders_data = {}
        # If job was created, file is already validated
        string_io = StringIO.StringIO(base64.decodestring(self.file_data))
        csv_reader = csv.reader(string_io, delimiter=',', quotechar='"')

        # At this point header is already validated and present,
        # we just fetch it and move the reader's cursor
        header = None
        starting_row = 0
        for row in range(3):
            header = csv_reader.next()
            starting_row += 1
            if header == et.EBAY_CSV_HEADERS:
                break

        # Loop through the rows and gather the results
        for row in csv_reader:
            mapped_results = dict(zip(header, row))
            raw_orders_data.append(mapped_results)

        # Prepare file import error string
        file_import_errors = invoice_creation_errors = str()

        validated_order_ids = []
        # Loop through mapped results and check what invoices need to be updated
        for line_number, raw_order_data in enumerate(raw_orders_data, 1 + starting_row):
            # If all columns are empty, do not display an error
            # Just skip this line altogether.
            if all(not col for col in raw_order_data.values()):
                continue
            # Check base order constraints, and skip if any
            record_import_errors = self.check_import_constraints(
                raw_order_data, line_number, validated_order_ids,
            )
            if record_import_errors:
                file_import_errors += record_import_errors
                continue

            ext_order_id = raw_order_data.get('Order Number')
            if ext_order_id not in validated_order_ids:
                validated_order_ids.append(ext_order_id)
            # Check whether current order exists
            ebay_order = self.env['ebay.order'].search([('ext_order_id', '=', ext_order_id)])
            if ebay_order:
                # If update present data flag is not set, skip
                if not update_present_data:
                    continue
                # Otherwise, we unlink the invoice and
                # the order to later recreate them
                invoice = ebay_order.invoice_id
                invoice.action_invoice_cancel_draft()
                invoice.write({'move_name': False, 'number': False, 'name': False})
                invoice.unlink()
                ebay_order.unlink()

            # If there's already a line in order data with this number, we parse following CSV
            # line interpreting it as an order line of principal product
            structured_data = structured_orders_data.get(ext_order_id)
            if structured_data:
                parsed_order_lines = self.parse_order_line_values(raw_order_data)
                structured_data['ebay_order_line_ids'].extend(parsed_order_lines)
            else:
                order_data = self.parse_order_values(raw_order_data)
                # Save the first occurring CSV line of the order
                order_data['line_number'] = line_number
                structured_orders_data[ext_order_id] = order_data

        # Create the orders from processed data
        for structured_order_data in structured_orders_data.values():
            line_number = structured_order_data.pop('line_number')
            try:
                created_order = EbayOrder.create(structured_order_data)
                created_order.check_constraints(raise_exception=True)
                created_order.create_invoices(raise_exception=True)
            except Exception as exc:
                self.env.cr.rollback()
                file_import_errors += _(
                    'Failed to create the order due to following errors - {}. line number - {}\n'
                ).format(str(exc.args), line_number)
                continue

            # Append it to the main list and commit
            created_orders |= created_order
            self.env.cr.commit()

        # Prepare base job data
        base_job_data = {
            'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'created_order_ids': [(4, order.id) for order in created_orders],
        }
        # Determine the state based on file import errors
        if file_import_errors or invoice_creation_errors:
            # Gather file import and invoice creation errors
            execution_errors = str()
            if file_import_errors:
                execution_errors += _('File import errors:\n\n {} \n\n').format(file_import_errors)
            if invoice_creation_errors:
                execution_errors += _('Invoice creation errors:\n\n {} \n\n').format(invoice_creation_errors)

            # Update current job
            base_job_data.update({
                'execution_errors': execution_errors,
                'execution_state': 'warning',
            })
        else:
            base_job_data.update({'execution_state': 'finished', })

        # Update the job
        self.write(base_job_data)

    @api.multi
    def check_import_constraints(self, raw_order_data, line_number, validated_order_ids):
        """
        Check base constraints before parsing the order any further
        :param raw_order_data: dict: Parsed raw order data
        :param line_number: int: Number of the CSV line
        :param validated_order_ids: List of external IDs that already passed constraint checks
        :return: str: Import errors
        """

        # Base objects - Important to add context to country, so name is not translated
        ResCountry = self.env['res.country'].with_context(lang='en_US').sudo()
        EbayCurrencyMapper = self.env['ebay.currency.mapper']

        record_import_errors = str()

        ext_order_id = raw_order_data.get('Order Number')
        # If there's no order ID, do not check any further data
        if not ext_order_id:
            record_import_errors += _('Missing order ID. line number - {}\n').format(line_number)
            return record_import_errors

        # Ebay passes several lines with the same order ID, and only the first line contains
        # all the order data, other lines are meant to represent inner order lines, thus
        # we only check constraints of the first occurrence.
        if ext_order_id in validated_order_ids:
            return record_import_errors

        # Check if country name exists and is correct
        buyer_country = raw_order_data.get('Buyer Country')
        if not buyer_country:
            record_import_errors += _('Missing buyer country. line number - {}\n').format(line_number)
        if buyer_country:
            country_count = ResCountry.search_count([('name', '=', buyer_country)])
            if not country_count:
                country_count = ResCountry.search_count([('name', 'like', buyer_country)])
            if not country_count or country_count > 1:
                record_import_errors += _('Country name is incorrect. line number - {}\n').format(line_number)

        # Check if buyer name exists
        buyer_name = raw_order_data.get('Buyer Name')
        if not buyer_name:
            record_import_errors += _('Missing buyer name. line number - {}\n').format(line_number)

        # Check if external currency code exists and whether mapper for it is already created
        principal_amount, ext_currency_code = parse_numeric_value_currency(
            raw_order_data.get('Sold For', 0.0))

        if not ext_currency_code:
            record_import_errors += _('Missing external currency code. line number - {}\n').format(line_number)
        if ext_currency_code and not EbayCurrencyMapper.search_count([('external_code', '=', ext_currency_code)]):
            record_import_errors += _(
                'Mapper for external currency code {} does not exist. line number - {}\n'
            ).format(ext_currency_code, line_number)

        return record_import_errors

    @api.multi
    def parse_order_values(self, ext_order_values):
        """
        Parses order values from passed CSV file and
        groups them into a structure for record creation
        :return: dict: Parsed data
        """
        self.ensure_one()

        # Parse order lines
        order_lines = self.parse_order_line_values(ext_order_values)
        # Parse rest of the order data
        order_date_dt = parse(ext_order_values.get('Sale Date'))
        order_date = order_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        try:
            ship_date_dt = parse(ext_order_values.get('Shipped On Date'))
            shipping_date = ship_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            shipping_date = False

        order_data = {
            'ext_order_id': ext_order_values.get('Order Number'),
            'ext_sale_id': ext_order_values.get('Sales Record Number'),
            'buyer_name': ext_order_values.get('Buyer Name'),
            'buyer_address': ext_order_values.get('Buyer Address 1'),
            'buyer_vat': ext_order_values.get('Buyer Tax Identifier Value'),
            'destination_country_name': ext_order_values.get('Buyer Country'),
            'origin_country_id': self.origin_country_id.id,
            'order_date': order_date,
            'shipping_date': shipping_date,
            'ext_currency_code': ext_order_values.get('ext_currency_code'),
            'ebay_order_line_ids': order_lines,
        }
        return order_data

    @api.multi
    def parse_order_line_values(self, ext_order_values):
        """
        Parses order line values based on different sum columns.
        Each line is split per one sum column
        :param ext_order_values: dict: CSV parsed order values
        :return: list: Structured order lines
        """

        order_lines = []
        base_quantity = 1

        # Get and parse all the amounts, first parse is including currency
        principal_amount, ext_currency_code = parse_numeric_value_currency(
            ext_order_values.get('Sold For', 0.0))

        # We update main order values with parsed currency code if key is not there
        if not ext_order_values.get('ext_currency_code'):
            ext_order_values.update({
                'ext_currency_code': ext_currency_code,
            })

        # Quantity is only applicable to principal amount
        # all other lines use base 1 quantity
        quantity = parse_numeric_value(
            ext_order_values.get('Quantity', base_quantity))

        shipping_amount = parse_numeric_value(
            ext_order_values.get('Shipping And Handling', 0.0))
        collected_tax_amount = parse_numeric_value(
            ext_order_values.get('eBay Collected Tax', 0.0))

        principal_item_code = ext_order_values.get('Item Number')
        # Append first, main principal line if principal item code exists
        if principal_item_code:
            order_lines.append((0, 0, {
                'name': _('eBay - Main amount'),
                'line_type': 'main',
                'ext_product_code': principal_item_code,
                'price_unit': principal_amount,
                'quantity': quantity,
            }))

        if not tools.float_is_zero(shipping_amount, precision_digits=2):
            # Append shipping line
            order_lines.append((0, 0, {
                'name': _('eBay - Shipping amount'),
                'line_type': 'shipping',
                'price_unit': shipping_amount,
                'quantity': base_quantity,
            }))

        if not tools.float_is_zero(collected_tax_amount, precision_digits=2):
            # Append shipping line
            order_lines.append((0, 0, {
                'name': _('eBay - Collected taxes'),
                'line_type': 'collected_taxes',
                'price_unit': collected_tax_amount,
                'quantity': base_quantity,
            }))

        return order_lines

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('eBay order CSV job - %s') % x.id) for x in self]
