# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from lxml import etree
from lxml.etree import tostring
from itertools import chain
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pyodbc
from xml.etree.ElementTree import tostring
import pytz


class RasoExportWizard(models.TransientModel):

    _name = 'raso.export.wizard'

    def _date_from_default(self):
        return datetime.now(pytz.timezone('Europe/Vilnius')) - relativedelta(months=1)

    def _date_to_default(self):
        return datetime.now(pytz.timezone('Europe/Vilnius'))

    data_type = fields.Selection([('0', 'Pardavimai'),
                                  ('1', 'Sąskaitos Faktūros'),
                                  ('2', 'Tara'),
                                  ('3', 'Grąžinimai'),
                                  ('4', 'Visi')],
                                 required=True, string='Duomenų tipas exportuojamas iš RASO', default='4')
    use_date = fields.Boolean(string='Leisti naudoti pasirinktas datas', default=False)
    get_status_one_rows = fields.Boolean(string=_('Įtraukti panaudotus duomenis (Status = 1)'), default=False)
    date_from = fields.Datetime(string='Duomenys nuo', default=_date_from_default)
    date_to = fields.Datetime(string='Duomenys iki', default=_date_to_default)

    @api.model
    def get_cursor(self, raise_exception=True):
        """
        Connect to external Raso Retail database using config parameters
        and get cursor object for query execution.
        :param raise_exception: Indicates whether exception should be raised on connection error
        :return: pyo-dbc cursor object/None
        """
        config_obj = self.sudo().env['ir.config_parameter']
        cursor = None

        # Get Raso Retail config parameters
        server = config_obj.get_param('raso_server')
        db = config_obj.get_param('raso_db')
        user = config_obj.get_param('raso_user')
        password = config_obj.get_param('raso_password')
        port = config_obj.get_param('raso_port')

        try:
            # Try connecting to external RR server
            conn = pyodbc.connect(
                "DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s" % (
                    server, port, db, user, password))
            cursor = conn.cursor()

        except Exception as exc:
            # Pyo-dbc exception. If user is admin, display the full error message
            if raise_exception:
                error_template = _('Nepavyko pasiekti išorinio Raso Retail serverio. Patikrinkite serverio statusą.')
                if self.env.user.has_group('base.group_system'):
                    error_template += _(' Klaidos pranešimas: {}').format(exc.args[1])
                raise exceptions.UserError(error_template)

        return cursor

    def get_query(self, data_type):
        db = self.sudo().env['ir.config_parameter'].get_param('raso_db')
        if self.get_status_one_rows:
            domain = [('data_type', '=', data_type)]
            if self.use_date:
                domain += [
                    ('sale_date', '<=', self.date_to),
                    ('sale_date', '>=', self.date_from)
                ]
            if self.env['raso.sales'].search(domain, count=True) > 0:
                raise exceptions.UserError('Negalima naudoti panaudotų duomenų opcijos turint duomenų,'
                                           ' ištrinkite visus pardavimus/grąžinimus jeigu norite naudoti šią opciją')
            return "SELECT * FROM [" + db + "].[ie].[SyncDataExport] WHERE DataType = %s" % data_type
        else:
            return "SELECT * FROM [" + db + "].[ie].[SyncDataExport] WHERE DataType = %s and status != 1" % data_type

    def cron_job_export(self):
        wizard = self.env['raso.export.wizard'].create({})
        wizard.with_context(cron_job=True).cron_get_data()

    @api.model
    def cron_job_recreate(self):
        """
        Cron-job that (re)creates system objects (invoices-moves-inventories) from Raso Retail data.
        :return: None
        """

        def get_lock_domain(date_field):
            return [(date_field, '>', lock_date)] if lock_date else []

        # Get the lock date and build base domains
        lock_date = self.sudo().env.user.company_id.get_user_accounting_lock_date()

        # Check for any sales to split
        sales_to_split = self.env['raso.sales'].search(
            [('inventory_id', '=', False), ('invoice_line_id', '=', False)]
        )
        if sales_to_split:
            sales_to_split.split_zero_amount_sale()

        # Collect sales and external invoices to invoice
        inv_to_invoice = self.env['raso.invoices'].search(
            [('invoice_id', '=', False)] + get_lock_domain('raso_invoice_line_ids.sale_date')
        )
        if inv_to_invoice:
            inv_to_invoice.create_invoices()

        sales_to_invoice = self.env['raso.sales'].search([
            ('invoice_line_id', '=', False),
            ('zero_amount_sale', '=', False),
            ('zero_manual_amount_sale', '=', False),
        ] + get_lock_domain('sale_date'))
        if sales_to_invoice:
            sales_to_invoice.create_invoices()

        # Collect payments to move
        payments_to_create = self.env['raso.payments'].search([
            ('move_id', '=', False),
            ('state', 'in', ['active', 'warning']),
            ('payment_type_id.is_active', '=', True),
        ] + get_lock_domain('payment_date'))
        if payments_to_create:
            payments_to_create.move_creation_prep()

        # Collect payments to reconcile (no lock date filtering for reconciliations)
        payments_to_reconcile = self.env['raso.payments'].search([
            ('move_id', '!=', False),
            ('state', 'in', ['open', 'partially_reconciled']),
            ('payment_type_id.do_reconcile', '=', True),
        ])
        if payments_to_reconcile:
            payments_to_reconcile.reconcile_payments()

        # Collect sales to write-off
        sales_to_write_off = self.env['raso.sales'].search([
            ('inventory_id', '=', False),
            ('state', 'in', ['imported', 'failed_inventory', 'failed']),
            '|', ('zero_amount_sale', '=', True), ('zero_manual_amount_sale', '=', True),
        ] + get_lock_domain('sale_date'))
        if sales_to_write_off:
            sales_to_write_off.create_inventory_write_off_prep()

    @api.model
    def parse_xml(self, data):
        """
        Parse fetched XML file from RasoRetail and prepare data for object creation
        :param data: dict of data fetched from RasoRetail
        :return: Fetched values
        """
        def split_manual_lines(node_line, object_values, object_list, children=True):
            """
            Split one node line into two lines if manual and regular quantities
            are of different signs.
            :param node_line: XML data line
            :param object_values: values of single to-be-created record
            :param children: signifies how values should be appended (0, 0, vals) or vals
            :param object_list: list of values for to-be-created records
            :return: None
            """
            quantity = float(stringify_children(node_line.find('QTY')))
            quantity_man = float(stringify_children(node_line.find('QTYMANUAL')))

            # If quantity is different from manual quantity -- Split the line into two
            if tools.float_compare(0, quantity * quantity_man, precision_digits=2) > 0:
                object_values_manual = object_values.copy()
                object_values_manual.update({
                    'qty_man': quantity_man,
                    'vat_sum_man': float(stringify_children(node_line.find('VATSUMMANUAL'))),
                    'amount_man': float(stringify_children(node_line.find('AMOUNTMANUAL'))),
                })
                object_values.update({
                    'qty': quantity,
                    'vat_sum': float(stringify_children(node_line.find('VATSUM'))),
                    'amount': float(stringify_children(node_line.find('AMOUNT'))),
                })
                if children:
                    object_list.append((0, 0, object_values_manual))
                else:
                    object_list.append(object_values_manual)
            else:
                object_values.update({
                    'qty': quantity,
                    'qty_man': quantity_man,
                    'vat_sum': float(stringify_children(node_line.find('VATSUM'))),
                    'vat_sum_man': float(stringify_children(node_line.find('VATSUMMANUAL'))),
                    'amount': float(stringify_children(node_line.find('AMOUNT'))),
                    'amount_man': float(stringify_children(node_line.find('AMOUNTMANUAL'))),

                })
            if children:
                object_list.append((0, 0, object_values))
            else:
                object_list.append(object_values)

        def stringify_children(node):
            if node is not None:
                parts = ([node.text] +
                         list(chain(*([c.text, tostring(c), c.tail] for c in node.getchildren()))) +
                         [node.tail])
                return ''.join(filter(None, parts)).strip()
            else:
                return False

        if data['DataType'] == 0 or data['DataType'] == 3:
            try:
                root = etree.fromstring(data['SyncData'].encode('utf-8'))
                shop_no = root.get('ShopNo')
                pos_no = root.get('PosNo')
                last_z = root.get('LASTZ')
                sales = root.findall('.//Sales')
                payments = root.findall('.//Payments')
                res = {}
                sale_lines = []
                payment_lines = []
                res['payment_lines'] = payment_lines
                res['sale_lines'] = sale_lines
                sale_date = False
                for line in sales:
                    data_type = str(data['DataType'])
                    sale_date = stringify_children(line.find('SALEDATE'))
                    sale_line = {
                        'data_type': data_type,
                        'shop_no': shop_no,
                        'pos_no': pos_no,
                        'last_z': last_z,
                        'sale_date': sale_date,
                        'code': stringify_children(line.find('CODE')),
                        'name': stringify_children(line.find('NAME')),
                        'discount': float(stringify_children(line.find('DISCOUNT'))),
                    }
                    # Split sale line into two if manual and regular quantities differ
                    split_manual_lines(line, sale_line, sale_lines, children=False)

                for line in payments:
                    if not stringify_children(line.find('QTY')):
                        qty = 0
                    else:
                        qty = float(stringify_children(line.find('QTY')))
                    if not stringify_children(line.find('AMOUNT')):
                        amount = 0
                    else:
                        amount = float(stringify_children(line.find('AMOUNT')))
                    payment_line = {
                        'code': stringify_children(line.find('CODE')),
                        'qty': qty,
                        'amount': amount,
                        'shop_no': shop_no,
                        'pos_no': pos_no,
                        'payment_date': sale_date,
                    }
                    payment_lines.append(payment_line)
                return 1, res
            except ValueError:
                return 3, []

        if data['DataType'] == 1:
            try:
                root = etree.fromstring(data['SyncData'].encode('utf-8'))
                shop_no = root.get('ShopNo')
                pos_no = root.get('PosNo')
                last_z = root.get('LASTZ')
                invoice_no = root.get('InvoiceNo')
                partner_code = root.get('PartnerCode')
                partner_name = root.get('PartnerName')
                partner_vat = root.get('PartnerVATCode')
                partner_address = root.get('PartnerAddress')
                invoice_sales = root.findall('.//Sales')
                invoice_payments = root.findall('.//Payments')
                res = {}
                invoice_lines = []
                payment_lines = []
                res['raso_payment_line_ids'] = payment_lines
                res['raso_invoice_line_ids'] = invoice_lines
                res['invoice_no'] = invoice_no
                res['partner_code'] = partner_code
                res['partner_name'] = partner_name
                res['partner_vat'] = partner_vat
                res['partner_address'] = partner_address
                res['shop_no'] = shop_no
                res['pos_no'] = pos_no
                res['last_z'] = last_z
                sale_date = False
                for line in invoice_sales:
                    sale_date = stringify_children(line.find('SALEDATE'))
                    invoice_line = {
                        'raso_invoice_number': invoice_no,
                        'sale_date': sale_date,
                        'code': stringify_children(line.find('CODE')),
                        'name': stringify_children(line.find('NAME')),
                        'discount': float(stringify_children(line.find('DISCOUNT'))),
                    }

                    # Split invoice line into two if manual and regular quantities differ
                    split_manual_lines(line, invoice_line, invoice_lines)

                for line in invoice_payments:
                    try:
                        amount = float(stringify_children(line.find('AMOUNT')))
                        qty = float(stringify_children(line.find('AMOUNT')))
                        payment_line = {
                            'code': stringify_children(line.find('CODE')),
                            'qty': qty,
                            'amount': amount,
                            'shop_no': shop_no,
                            'pos_no': pos_no,
                            'payment_date': sale_date,
                        }
                        payment_lines.append((0, 0, payment_line))
                    except ValueError:
                        continue
            except ValueError:
                return 3, []
            return 1, res

        if data['DataType'] == 2:
            try:
                root = etree.fromstring(data['SyncData'].encode('utf-8'))
                shop_no = root.get('ShopNo')
                pos_no = root.get('PosNo')
                last_z = root.get('LASTZ')
                tara = root.findall('.//Tara')
                payments = root.findall('.//Payments')
                res = {}
                sale_lines = []
                payment_lines = []
                res['payment_lines'] = payment_lines
                res['sale_lines'] = sale_lines

                for line in tara:
                    sale_line = {
                        'data_type': str(data['DataType']),
                        'shop_no': shop_no,
                        'pos_no': pos_no,
                        'last_z': last_z,
                        'sale_date': stringify_children(line.find('TARADATE')),
                        'code': stringify_children(line.find('CODE')),
                        'name': stringify_children(line.find('NAME')),
                        'qty': float(stringify_children(line.find('QTY'))),
                        'amount': float(stringify_children(line.find('AMOUNT'))),
                        'discount': float(stringify_children(line.find('DISCOUNT'))),
                    }
                    sale_lines.append(sale_line)

                for line in payments:
                    if not stringify_children(line.find('QTY')):
                        qty = 0
                    else:
                        qty = float(stringify_children(line.find('QTY')))
                    if not stringify_children(line.find('AMOUNT')):
                        amount = 0
                    else:
                        amount = float(stringify_children(line.find('AMOUNT')))
                    payment_line = {
                        'code': stringify_children(line.find('CODE')),
                        'qty': qty,
                        'amount': amount,
                    }
                    payment_lines.append(payment_line)
            except ValueError:
                return 3, []

            return 1, res

    @api.multi
    def has_existing_data(self):
        self.ensure_one()

        # Check existing sales
        sales_domain = []
        invoice_domain = []
        payment_domain = []

        # Filter by dates if dates are used
        if self.use_date and self.date_from and self.date_to:
            sales_domain += [
                ('sale_date', '<=', self.date_to),
                ('sale_date', '>=', self.date_from)
            ]
            invoice_domain += [
                ('raso_invoice_line_ids.sale_date', '<=', self.date_to),
                ('raso_invoice_line_ids.sale_date', '>=', self.date_from)
            ]
            payment_domain += [
                ('payment_date', '<=', self.date_to),
                ('payment_date', '>=', self.date_from)
            ]

        has_sales = self.env['raso.sales'].search_count(sales_domain)
        has_invoices = self.env['raso.invoices'].search_count(invoice_domain)
        has_payments = self.env['raso.payments'].search_count(payment_domain)
        return has_sales or has_invoices or has_payments

    @api.multi
    def _should_be_skipped_by_use_date(self, date_to_check):
        self.ensure_one()
        should_be_skipped = False
        if self.use_date and self.date_from and self.date_to and date_to_check:
            # Skip sales from other dates if date filter is used
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            try:
                payment_date_dt = datetime.strptime(date_to_check, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except:
                payment_date_dt = datetime.strptime(date_to_check, tools.DEFAULT_SERVER_DATE_FORMAT)
            if not (date_from_dt <= payment_date_dt <= date_to_dt):
                should_be_skipped = True
        return should_be_skipped

    @api.multi
    def cron_get_data(self):
        self.ensure_one()
        db = self.sudo().env['ir.config_parameter'].get_param('raso_db')
        if self.data_type == '4':
            if self.get_status_one_rows:
                if self.has_existing_data():
                    raise exceptions.UserError(
                        _('Negalima naudoti panaudotų duomenų opcijos turint duomenų, ištrinkite visus '
                          '(sąskaitas, pardavimus ir mokėjimus) duomenis jeigu norite naudoti šią opciją'))
                sql = "SELECT * FROM [" + db + "].[ie].[SyncDataExport]"
            else:
                sql = "SELECT * FROM [" + db + "].[ie].[SyncDataExport] WHERE status != 1"
        else:
            sql = self.get_query(self.data_type)

        cursor = self.get_cursor()
        cursor.execute(sql)
        r_data = [dict(zip(zip(*cursor.description)[0], row)) for row in cursor.fetchall()]

        def check_validity(data):
            if data['SyncDataExportId'] and data['DataProvider'] and data['SyncData'] and row['DataType'] is not None:
                if not isinstance(row['SyncDataExportId'], int):
                    return False
                if not isinstance(data['DataType'], int):
                    return False
                if not 0 <= data['DataType'] <= 3:
                    return False
                return True
            else:
                return False

        failed_rows = 0
        for row in r_data:
            sql = "EXEC [" + db + "].[ie].[usp_SyncDataExport_u] @SyncDataExportId=?, @Status=?"
            cursor.execute(sql, [row['SyncDataExportId'], 2])
            cursor.commit()
            if check_validity(row):
                status, values = self.parse_xml(row)
                if status == 1:
                    status = 1
                    sync_data_export_id = row['SyncDataExportId']
                    data_type = row['DataType']
                    sync_data = row['SyncData']
                    if row['DataType'] in [0, 2, 3]:
                        for line in values['sale_lines']:
                            if self._should_be_skipped_by_use_date(line.get('sale_date')):
                                continue
                            self.env['raso.sales'].sudo().create(line)
                            self.env.cr.commit()

                        for line in values['payment_lines']:
                            if self._should_be_skipped_by_use_date(line.get('payment_date')):
                                continue
                            self.env['raso.payments'].sudo().create(line)
                            self.env.cr.commit()

                    if row['DataType'] == 1:
                        payment_lines = values.get('raso_payment_line_ids', list())
                        invoice_lines = values.get('raso_invoice_line_ids', list())
                        should_be_skipped = \
                            any(self._should_be_skipped_by_use_date(l[2].get('payment_date')) for l in payment_lines) or \
                            any(self._should_be_skipped_by_use_date(l[2].get('sale_date')) for l in invoice_lines)
                        if not should_be_skipped:
                            self.env['raso.invoices'].sudo().create(values)
                            self.env.cr.commit()

                    if row['Status'] == 3:
                        export = self.env['sync.data.export'].search(
                            [('sync_data_export_id', '=', sync_data_export_id)])
                        if export:
                            export.write({
                                'status': status,
                            })
                    else:
                        self.env['sync.data.export'].create({
                            'status': status,
                            'sync_data_export_id': sync_data_export_id,
                            'data_type': str(data_type),
                            'sync_data': sync_data,
                        })

                    args = [sync_data_export_id, status]
                    sql = "EXEC [" + db + "].[ie].[usp_SyncDataExport_u] @SyncDataExportId=?, @Status=?"
                    cursor.execute(sql, args)
                    cursor.commit()
                else:
                    self.update_status(row, cursor, status)
                    failed_rows += 1
            else:
                self.update_status(row, cursor, 3)
                failed_rows += 1

        if failed_rows:
            body = _('Klaida importuojant %s eilučių/es') % failed_rows
            self.send_bug(body)

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': 'RASO importavimo klaidos [%s]' % self._cr.dbname,
            'error_message': body,
            'date': datetime.now(pytz.timezone('Europe/Vilnius')).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        })

    def post_message(self, obj, body, state):
        send = {
            'body': body,
        }
        for line in obj:
            line.message_post(**send)
        obj.write({'state': state})

    def update_status(self, row, cursor, status):
        db = self.sudo().env['ir.config_parameter'].get_param('raso_db')
        sync_data_export_id = row['SyncDataExportId']
        data_type = row['DataType']
        sync_data = row['SyncData']
        self.env['sync.data.export'].create({
            'status': status,
            'sync_data_export_id': sync_data_export_id,
            'data_type': str(data_type),
            'sync_data': sync_data,
        })
        args = [sync_data_export_id, status]
        sql = "EXEC [" + db + "].[ie].[usp_SyncDataExport_u] @SyncDataExportId=?, @Status=?"
        cursor.execute(sql, args)
        cursor.commit()


RasoExportWizard()