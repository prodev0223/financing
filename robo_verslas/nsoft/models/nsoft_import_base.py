# -*- coding: utf-8 -*-
from odoo import models, api, _, tools, exceptions
from dateutil.relativedelta import relativedelta
from .. models import nsoft_tools as nt
from datetime import datetime
import psycopg2
import logging

_logger = logging.getLogger(__name__)


class NsoftImportBase(models.AbstractModel):

    _name = 'nsoft.import.base'
    _description = 'Abstract model that contains all nSoft connectors and data fetchers'

    # -----------------------------------------------------------------------------------------------------------------
    # BASE-INTEGRATION Fetchers ---------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def fetch_invoices(self, cursor, date_from=None, date_to=None):
        """
        Base method that is used to fetch external nSoft invoices
        :param cursor: nSoft DBs' SQL Cursor object
        :param date_from: str: Date from invoice fetch
        :param date_to: str: Date to invoice fetch
        :return: None
        """
        # Prepare base data
        query_template = '''
        SELECT * FROM web.view_invoices 
        WHERE lng_code like 'lit' 
        AND payment_name IS NOT NULL
        '''
        executable_sql = query_template
        params = tuple()

        NsoftInvoice = created_invoices = self.env['nsoft.invoice'].sudo()
        if date_from and date_to:
            executable_sql = query_template + '''AND created_at between %s and %s'''
            params = (date_from, date_to,)
        elif date_from:
            executable_sql = query_template + '''AND created_at >= %s'''
            params = (date_from,)

        cursor.execute(executable_sql, params)
        data = cursor.fetchall()
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]

        for rec in records:
            values = {
                'name': rec.get('name') or False,
                'partner_address': rec.get('buyer_address') or False,
                'partner_bank_account': (rec.get('buyer_bank_account') or '').strip(),
                'partner_bank_code': (rec.get('buyer_bank_code') or '').strip(),
                'partner_code': (rec.get('buyer_code') or '').strip(),
                'partner_name': (rec.get('buyer_name') or '').strip(),
                'partner_vat': (rec.get('buyer_vat') or '').strip(),
                'cash_register_number': (rec.get('cash_register_numbers') or '').strip(),
                'date_invoice': (rec.get('created_at') or '').strip(),
                'date_due': (rec.get('payment_due') or '').strip(),
                'ext_id': rec.get('doc_id') or 0,
                'receipt_id': (rec.get('cheque_ids') or '').strip(),
                'item_amount': rec.get('item_amount') or 0,
                'items_vat_sum': rec.get('item_vat_sum') or 0,
                'sum_with_vat': rec.get('item_sum_with_vat') or 0,
                'sum_wo_vat': rec.get('sum_wo_vat') or 0,
                'payment_name': (rec.get('payment_name') or '').strip(),
                'payment_date': rec.get('created_at')
            }
            # Continue if not external ID is provided and if invoice already exists in the system
            if not values['ext_id']:
                continue
            if NsoftInvoice.search_count([('ext_id', '=', values['ext_id'])]):
                continue
            # Create the invoice
            created_invoice = NsoftInvoice.sudo().create(values)
            if not created_invoice:
                body = _('Klaida kuriant sąskaitą eilutę, trūksta parametrų iš nsoft DB')
                self.send_bug(body)
                continue
            created_invoices |= created_invoice

        # Gather all the receipts from the invoices, and fetch all the payments
        receipts = created_invoices.filtered(lambda r: r.receipt_id).mapped('receipt_id')
        if receipts:
            payments = self.fetch_related_payments(cursor, receipts)
            for invoice in created_invoices:
                invoice.write({'nsoft_payment_ids': payments.get(invoice.receipt_id, [])})

    @api.model
    def get_sale_line_fetch_query(self, date_from=None, date_to=None):
        """
        Builds sale line fetch query based on the provided date range
        @param date_from: (str) optional period start
        @param date_to: (str) optional period end
        @return: (str) - the query and (tuple) - query parameters
        """
        query = '''SELECT * FROM reports.view_sales_all AS sales WHERE sales.payment_time '''
        if date_from and date_to:
            query += '''between %s and %s'''
            params = (date_from, date_to,)
        elif date_from:
            query += '''>= %s'''
            params = (date_from,)
        elif date_to:
            query += '''<= %s'''
            params = (date_to,)
        else:
            query += '''IS NOT NULL'''
            params = tuple()
        return query, params

    @api.model
    def process_fetched_sale_line_data(self, sale_line_data):
        """
        Processes sale line data to build a dictionary of parameters suitable for nsoft.sale.line creation
        @param sale_line_data: (dict) fetched sale line data from nsoft
        @return: (dict) processed nsoft sale line data
        """
        sale_time = sale_line_data.get('sale_time') or ''
        payment_type_code = sale_line_data.get('payment_type_code')
        return {
            'receipt_id': sale_line_data.get('cheque_id') or '',
            'ext_sale_id': sale_line_data.get('sale_id'),
            'product_code': (sale_line_data.get('item_code') or '').strip(),
            'cash_register_number': (sale_line_data.get('cash_register_no') or '').strip(),
            'sale_price': sale_line_data.get('sale_price') or 0,
            'payment_sum': sale_line_data.get('payment_sum') or 0,
            'quantity': sale_line_data.get('sale_item_count') or 0,
            'ext_cash_register_id': sale_line_data.get('sale_point_id') or 0,
            'sale_date': sale_time,
            'payment_due': sale_line_data.get('payment_due') or '',
            'vat_rate': sale_line_data.get('vat_rate') or 0,
            'vat_code': sale_line_data.get('vat_code') or '',
            'sale_type': sale_line_data.get('sale_type_name') or '',
            'payment_type_code': payment_type_code[0] if payment_type_code else '',
            'ext_product_category_id': sale_line_data.get('category_id', 0),
            'payment_date': sale_time  # Field in the model is datetime unlike the one above
        }

    @api.model
    def fetch_sale_lines(self, cursor, date_from=None, date_to=None):
        """
        Base method that is used to fetch external nSoft sale lines
        :param cursor: nSoft DBs' SQL Cursor object
        :param date_from: str: Date from invoice fetch
        :param date_to: str: Date to invoice fetch
        :return: None
        """
        # Create reference to nsoft sale line environment and create a sale line accumulator
        NsoftSaleLine = created_sales = self.env['nsoft.sale.line']

        # Get SQL query, its parameters and fetch the records
        executable_sql, params = self.get_sale_line_fetch_query(date_from, date_to)
        try:
            cursor.execute(executable_sql, params)
            data = cursor.fetchall()
        except Exception as e:
            full_query = executable_sql % params
            raise exceptions.UserError('Failed to fetch nsoft sale lines.\n\nQuery - {}.\n\nError - {}'.format(
                full_query, e.args[0]
            ))

        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]

        # Find existing, already imported sale line identifiers
        external_sale_identifiers = [rec.get('sale_id') for rec in records if rec.get('sale_id')]
        existing_sale_identifiers = NsoftSaleLine.search([
            ('ext_sale_id', 'in', external_sale_identifiers)
        ]).mapped('ext_sale_id')

        # Skip if there's no external sale ID or if record already exists in the system
        records_to_import = [
            rec for rec in records
            if rec.get('sale_id') and rec.get('sale_id') not in existing_sale_identifiers
        ]

        import_errors = []  # Import error accumulator

        for rec in records_to_import:
            # Prepare the sale line values
            sale_line_values = self.process_fetched_sale_line_data(rec)

            # Try to create the sale line
            sale_line = exception_message = None
            try:
                sale_line = NsoftSaleLine.sudo().create(sale_line_values)
            except Exception as e:
                exception_message = e.args[0]

            # Check if the sale line was created successfully
            if not sale_line:
                sale_identifier = sale_line_values.get('ext_sale_id')
                error_message = _('Įspėjimas kuriant pardavimo eilutę, trūksta parametrų iš nsoft DB ({})').format(
                    sale_identifier
                )
                if exception_message:
                    error_message += _('. Klaidos pranešimas - {}.').format(exception_message)
                import_errors.append(error_message)
                continue

            # Add sale line to created sales
            created_sales |= sale_line

        # Notify about failed sale line import
        if import_errors:
            self.send_bug('.\n'.join(import_errors))

        # Get the receipts from created sales and fetch related payments
        receipts = created_sales.filtered(lambda s: not s.nsoft_invoice_id and s.receipt_id).mapped('receipt_id')
        if receipts:
            payments = self.fetch_related_payments(cursor, receipts)
            for sale in created_sales:
                sale.write({'nsoft_payment_ids': payments.get(sale.receipt_id, [])})

    @api.model
    def fetch_remaining_lines(self, ext_invoice_ids):
        """
        Fetch nsoft invoice line objects from other table if nsoft invoice has no receipt.
        Create records and proceed with special invoice creation
        return: recordset: nsoft invoice line
        """
        NsoftInvoiceLine = created_records = self.env['nsoft.invoice.line']
        if not ext_invoice_ids:
            return created_records

        # Get the cursor and prepare the query
        cursor = self.get_external_cursor()

        sql = '''
        SELECT * FROM web.view_invoice_items AS inv_it 
        INNER JOIN view_prekes_kategorija kategorija ON inv_it.item_id = kategorija.prekes_id
        WHERE document_id in %s
        '''
        params = (tuple(ext_invoice_ids),)

        # Execute the query and fetch the records
        cursor.execute(sql, params)
        data = cursor.fetchall()
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]

        for rec in records:
            values = {
                'product_code': rec.get('code') or '',
                'ext_id': rec.get('id') or 0,
                'name': rec.get('item_name') or '',
                'quantity': rec.get('item_amount') or 0,
                'price_unit': rec.get('item_price') or 0,
                'vat_price': rec.get('price_with_vat') or 0,
                'discount': rec.get('item_discount') or 0,
                'vat_rate': rec.get('vat_rate') or 0,
                'ext_invoice_id': rec.get('document_id') or 0,
                'item_sum': rec.get('item_sum') or 0,
                'vat_sum': rec.get('vat_sum') or 0,
                'ext_product_category_id': rec.get('kat_id', 0)
            }
            # If external ID is not passed, just continue
            if not values['ext_id']:
                continue
            # Otherwise, check for duplicates and append it to created records if it's found
            invoice_line = NsoftInvoiceLine.search([('ext_id', '=', values['ext_id'])])
            if invoice_line:
                created_records |= invoice_line
                continue

            # Create nSoft invoice line
            try:
                invoice_line = NsoftInvoiceLine.sudo().create(values)
            except Exception as e:
                body = _('Klaida kuriant sąskaitos eilutę, klaida %s') % str(e.args[0])
                self.send_bug(body)
                continue
            created_records |= invoice_line

        self.env.cr.commit()
        return created_records

    @api.model
    def fetch_related_payments(self, cursor, receipts):
        """
        Fetch related payments from external nSoft DB for passed receipt IDs
        Create nsoft payment records
        :param cursor: nSoft DBs' SQL Cursor object
        :param receipts: receipts of related sale lines/invoices
        :return: dict: receipts by payment {'receipt_num': [(4, nsoft payment ID), ...], ...}
        """
        sql = '''
        SELECT mb_id AS ext_payment_type_id,
            ABS(mok_suma) AS payment_sum,
            mok_cekis AS receipt_id,
            mb_kodas AS payment_type_code
            FROM public.b_mokejimai AS pmt
                INNER JOIN b_mokejimo_budas AS pmt_type ON
                pmt.mok_budas = pmt_type.mb_id
                WHERE mok_cekis in %s AND mb_id <> 0
                AND pmt_type.mb_kodas not in %s
                AND mok_padengta = TRUE AND mok_suma <> 0
        '''
        cursor.execute(sql, (tuple(receipts), tuple(nt.PAYMENT_CODES_TO_SKIP),))
        data = cursor.fetchall()
        payments_by_receipt = {}
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]
        for record in records:
            receipt_id = str(record.get('receipt_id'))
            payment_vals = {
                'ext_payment_type_id': record.get('ext_payment_type_id'),
                'payment_sum': record.get('payment_sum'),
                'receipt_id': receipt_id,
                'payment_type_code': record.get('payment_type_code')
            }
            nsoft_payment = self.env['nsoft.payment'].create(payment_vals)
            if receipt_id not in payments_by_receipt:
                payments_by_receipt[receipt_id] = list()
            payments_by_receipt[receipt_id].append((4, nsoft_payment.id))
        return payments_by_receipt

    @api.model
    def fetch_cash_operation_data(self, cursor, date_from=None, date_to=None):
        """
        Fetches nSoft cash operation data and creates systemic records
        :param cursor: object: External cursor connection
        :param date_from: str: Date from which operations are fetched
        :param date_to: str: Date to which operations are fetched
        :return: None
        """

        # Check whether fetch should be executed
        company = self.env.user.company_id
        if not company.enable_nsoft_cash_operations:
            return

        NsoftCashOperation = self.env['nsoft.cash.operation'].sudo()
        # Build the query based on the synchronization date
        params = tuple()
        query_template = '''SELECT * FROM reports.view_cashin_cashout_operations AS cash_ops '''
        executable_sql = query_template + '''WHERE cash_ops.time IS NOT NULL'''
        if date_from and date_to:
            executable_sql = query_template + '''WHERE cash_ops.time between %s and %s'''
            params = (date_from, date_to,)
        elif date_from:
            executable_sql = query_template + '''WHERE cash_ops.time >= %s'''
            params = (date_from,)

        # Execute the query and format fetched data
        cursor.execute(executable_sql, params)
        data = cursor.fetchall()
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]

        pos_to_register_mapping = {}
        # Process fetched data
        for rec in records:
            # Yes, field name mistype in ext db..
            operation_type = rec.get('opertation_type')
            if not operation_type:
                continue

            ext_register_id = rec.get('point_of_sale', 0)
            cash_register_number = pos_to_register_mapping.get(ext_register_id)
            if not cash_register_number:
                query_template = '''
                SELECT cash_register_no FROM reports.view_sales_all 
                WHERE sale_point_id = %s LIMIT 1
                '''
                # Execute the query and format fetched data
                cursor.execute(query_template, (ext_register_id,))
                fetched_data = cursor.fetchone()
                cash_register_number = fetched_data[0] if fetched_data else None

            # Skip operations that do not have external register ID
            if not cash_register_number:
                continue
            pos_to_register_mapping.setdefault(ext_register_id, cash_register_number)

            # Get the external document ID and check for duplicates
            ext_document_id = rec.get('document')
            amount = rec.get('sum', 0.0)
            operation_date = rec.get('time', str())

            # If there's no external document ID, compose it using amount, timestamp and type
            if not ext_document_id:
                # Convert to numeric format and add it as a composite ID element
                date_repr = datetime.strptime(operation_date, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime('%s')
                ext_document_id = '{}-{}-{}'.format(operation_type, amount, date_repr)

            if NsoftCashOperation.search_count([('ext_document_id', '=', ext_document_id)]):
                continue

            # Prepare the values and create the cash operation
            values = {
                'ext_document_id': ext_document_id,
                'ext_register_id': ext_register_id,
                'cash_register_number': cash_register_number,
                'ext_cashier_id': rec.get('cashier', 0),
                'operation_date': operation_date,
                'operation_type': operation_type,
                'amount': amount,
                'receipt_number': rec.get('cash_receipt', str()),
                'fiscal_number': rec.get('fiscal_number', str()),
            }
            NsoftCashOperation.create(values)
            self.env.cr.commit()

    # -----------------------------------------------------------------------------------------------------------------
    # SUM-INTEGRATION Fetchers ----------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def fetch_create_sum_accounting(self):
        """
        Parent method that calls all the necessary sum accounting data fetchers:
        inventory acts, prime cost moves, and purchases.
        Search for failed/non-created records in the system, append to the newly
        fetched data and proceed to create system objects afterwards
        :return None
        """
        company = self.sudo().env.user.company_id
        # Check various constraints silently
        if not company.nsoft_accounting_type or company.nsoft_accounting_type not in ['sum']:
            return
        cursor = self.get_external_cursor()
        if not cursor:
            return
        sync_date = company.last_nsoft_db_sync or company.nsoft_accounting_threshold_date
        if not sync_date:
            return

        self.fetch_product_category_data(cursor)
        self.env.cr.commit()

        # Check whether purchase fetching is disabled in the system
        disable_purchase_fetching = self.env['ir.config_parameter'].sudo().get_param(
            'nsoft_sum_accounting_disable_purchase_fetching') == 'True'

        # Fetch all sum accounting data
        if not disable_purchase_fetching:
            self.fetch_purchases(cursor, sync_date)
        self.fetch_report_acts(cursor)

    @api.model
    def fetch_product_category_data(self, cursor):
        """
        Cron-job that is used if nsoft_accounting_type = sum. Fetches the product category line info
        :return: None
        """

        # Ref needed objects
        AccountAccount = self.env['account.account'].with_context(show_views=True)
        NsoftProductCategory = self.sudo().env['nsoft.product.category']

        sql = '''
            SELECT kat_id AS category_id, kat_pavadinimas AS category_name 
            FROM public.view_prekes_kategorija 
            WHERE kat_id IS NOT NULL GROUP BY category_id, category_name'''

        cursor.execute(sql)
        data = cursor.fetchall()
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]
        for rec in records:
            external_id = rec.get('category_id', 0)
            if NsoftProductCategory.search_count([('external_id', '=', external_id)]):
                continue
            values = {
                'name': rec.get('category_name', str()),
                'external_id': external_id,
            }
            NsoftProductCategory.create(values)

        # Adjust all nsoft accounts that became views, process is iterative
        # since setting one account as non view, can trigger another one
        # however it all normalizes out in the end
        account_domain = [('name', '=like', 'nSoft%'), ('is_view', '=', True)]
        while AccountAccount.search_count(account_domain):
            accounts = AccountAccount.search(account_domain)
            for account in accounts:
                account_code = NsoftProductCategory.get_account_account_number()
                account.write({'code': account_code})

    @api.model
    def fetch_purchases(self, cursor, date_from):
        """
        Fetch purchase objects from external nSoft DB, proceed with account.invoice creation
        :param cursor: nSoft DBs' SQL Cursor object
        :param date_from: date_from to use in the query
        :return: None
        """

        # Ref needed objects
        NsoftPurchaseInvoice = self.env['nsoft.purchase.invoice']

        purchase_query = """
        SELECT
            dok_id AS doc_id,
            dok_kodas AS invoice_number,
            dok_laikas AS create_date,
            dok_data AS date_invoice,
            dok_tipas AS invoice_type,
            tiekejo_vardas AS partner_name,
            tiekejo_pavarde AS partner_surname,
            tiekejo_kodas AS partner_code,
            tiekejo_pvm_kodas AS partner_vat,
            gavejo_pavadinimas AS warehouse_name,
            gavejo_kodas AS warehouse_code,
            dok_pastaba AS comments,
            category_id,
            sum_wo_vat,
            sum_w_vat,
            vat_sum,
            vat_rate
            FROM view_dok_pajamavimai 
            LEFT JOIN LATERAL (SELECT
                sums_total.category_id,
                sums_total.category_name,
                sums_total.sum_wo_vat,
                sums_total.sum_w_vat,
                sums_total.vat_sum,
                sums_total.vat_rate
                FROM(SELECT
                    b_perkelimai_detail.prd_dok,
                    b_perkelimai_detail.prd_pvm AS vat_rate,
                    categs.kat_id AS category_id, 
                    categs.kat_pavadinimas AS category_name,
                    SUM(COALESCE(b_perkelimai_detail.prd_suma_bm, 0::numeric)) AS sum_wo_vat,
                    SUM(COALESCE(b_perkelimai_detail.prd_suma_sm, 0::numeric)) AS sum_w_vat,
                    SUM(COALESCE(b_perkelimai_detail.prd_suma_sm::numeric - 
                                 b_perkelimai_detail.prd_suma_bm::numeric, 0::numeric)) AS vat_sum
                    FROM b_perkelimai_detail
                    INNER JOIN b_dok ON b_dok.dok_id = b_perkelimai_detail.prd_dok
                    INNER JOIN public.view_prekes_kategorija AS categs 
                        ON b_perkelimai_detail.prd_preke = categs.prekes_id
                    WHERE b_dok.dok_id = view_dok_pajamavimai.dok_id
                    GROUP BY b_perkelimai_detail.prd_dok, category_id, category_name, vat_rate) AS sums_total) 
                    final_res ON true
            WHERE view_dok_pajamavimai.dok_tipas in (3, 5) AND view_dok_pajamavimai.klb_kodas = 'eng' 
            AND view_dok_pajamavimai.dok_laikas >= %s"""

        # Execute the query and get the records
        cursor.execute(purchase_query, (date_from,))
        data = cursor.fetchall()
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]

        # Collect the invoice numbers
        invoice_numbers = set([x.get('invoice_number') for x in records])
        for invoice_number in invoice_numbers:
            # Get all the invoice lines, base data record acts as invoice data
            invoice_lines = [x for x in records if x.get('invoice_number') == invoice_number]
            data = invoice_lines[0]
            # Skip if we find an invoice that already exists in the system
            if NsoftPurchaseInvoice.search_count([('ext_invoice_id', '=', data.get('doc_id'))]):
                continue

            purchase_line_ids = []
            partner_name = '{} {}'.format(data.get('partner_name', str()), data.get('partner_surname', str()))
            invoice_type = data.get('invoice_type')
            if invoice_type in ['5']:
                # ROBO: Temp raise on type 5 until we encounter one, used to check the data
                # ROBO: and intentionally interrupt creation workflow
                raise exceptions.ValidationError(
                    'NSOFT TEST: Encountered purchase type 5: Create date - {}'.format(data.get('create_date')))
            # Prepare base values for the invoice
            vals = {
                'ext_invoice_id': data.get('doc_id'),
                'invoice_number': data.get('invoice_number'),
                'date_invoice': data.get('date_invoice'),
                'ext_create_date': data.get('create_date'),
                'partner_name': partner_name,
                'partner_code': data.get('partner_code'),
                'partner_vat': data.get('partner_vat'),
                'comments': data.get('comments'),
                'warehouse_name': data.get('warehouse_name'),
                'warehouse_code': data.get('warehouse_code'),
                'nsoft_purchase_invoice_line_ids': purchase_line_ids
            }
            # Prepare line values for the invoice
            for line in invoice_lines:
                line_vals = {
                    'ext_product_category_id': line.get('category_id'),
                    'amount_wo_vat': line.get('sum_wo_vat'),
                    'amount_w_vat': line.get('sum_w_vat'),
                    'amount_vat': line.get('vat_sum'),
                    'vat_rate': line.get('vat_rate'),
                }
                purchase_line_ids.append((0, 0, line_vals))
            # Create the invoice and commit
            NsoftPurchaseInvoice.create(vals)
            self.env.cr.commit()

    @api.model
    def fetch_report_acts(self, cursor):
        """
        Fetch report act data from external nSoft DB.
        Report acts include:
            - Inventory acts
            - Prime cost acts
            - Write-off acts
            - Period close acts
        Proceed with corresponding object creation in
        the system after the data is sanitized
        :param cursor: nSoft DBs' SQL Cursor object
        :return: None
        """

        # Always use threshold date, since reports can be updated
        date_from = self.env.user.sudo().company_id.nsoft_accounting_threshold_date
        if not date_from:
            return

        # Get report act data
        reports_data = self.fetch_base_report_data(cursor, date_from, doc_types=[6, 7, 9, 2])
        warehouse_ids = self.fetch_warehouses(cursor)

        duplicate_warnings = str()
        today_dt = datetime.now()
        for report_data in reports_data:
            ext_doc_id = report_data.get('doc_id')
            doc_type = report_data.get('doc_type')

            report_move = self.env['nsoft.report.move'].search([('ext_doc_id', '=', ext_doc_id)])
            if report_move:
                report_date_dt = datetime.strptime(report_move.report_date, tools.DEFAULT_SERVER_DATE_FORMAT)
                # If report is older than 60 days, we skip on find
                # otherwise we check for amount changes
                if (today_dt - report_date_dt).days > 60:
                    continue

            # Prepare the main report data
            nsoft_report_move_lines = []
            vals = {
                'report_date': report_data.get('doc_date'),
                'ext_doc_id': report_data.get('doc_id'),
                'report_type': doc_type,
                'ext_doc_number': report_data.get('ext_doc_number'),
                'ext_create_date': report_data.get('ext_create_date'),
                'nsoft_report_move_line_ids': nsoft_report_move_lines
            }

            # Fetch the lines of the report using a separate query
            inventory_query = self.get_main_sum_report_query()
            cursor.execute(inventory_query, {
                'date_from': date_from,
                'date_to': datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'warehouse_ids': tuple(warehouse_ids),
                'doc_id': ext_doc_id,
            })
            report_lines = cursor.fetchall()
            header = [col[0] for col in cursor.description]
            report_lines = [dict(zip(header, x)) for x in report_lines]

            # If lines do not exist, continue
            if not report_lines:
                continue

            total_move_amount = 0.0
            for line in report_lines:
                # Fetch warehouse data
                if not vals.get('ext_warehouse_id'):
                    vals.update({'ext_warehouse_id': line.get('warehouse_id')})

                if doc_type == nt.SPEC_SUM_DOC_TYPE:
                    # Get amounts and quantities
                    line_quantity = (line.get('start_qty') or 0.0) - (line.get('final_qty') or 0.0)
                    line_amount = (line.get('start_amount') or 0.0) - (line.get('final_amount') or 0.0)
                else:
                    # Get amounts and quantities
                    line_quantity = line.get(nt.REPORT_FIELD_NAME_MAPPING[doc_type]['qty']) or 0.0
                    line_amount = line.get(nt.REPORT_FIELD_NAME_MAPPING[doc_type]['amount']) or 0.0

                if not tools.float_is_zero(line_amount, precision_digits=2):
                    total_move_amount += line_amount
                    line_vals = {
                        'line_quantity': line_quantity,
                        'line_amount': line_amount,
                        'category_name': line.get('category_name'),
                        'product_name': line.get('product_name'),
                        'ext_product_category_id': line.get('category_id'),
                    }
                    nsoft_report_move_lines.append((0, 0, line_vals))

            # If report move exists, and newly fetched amount does not match the stored amount (with slight diff),
            # Unlink all of related account move records and report move itself.
            if report_move:
                difference = abs(report_move.total_move_amount - total_move_amount)
                if tools.float_compare(difference, 0.01, precision_digits=2) <= 0:
                    # If difference is less than or equal to 0.01, continue with next record
                    continue
                report_move.unlink_related_moves()
                report_move.unlink()

            # Only create the move if it contains at least one line
            if nsoft_report_move_lines:
                # Create report move records
                res = self.env['nsoft.report.move'].create(vals)
                if res.potential_duplicate:
                    res.delete_duplicate_moves()
                self.env.cr.commit()

        # Inform accountant about duplicates
        if duplicate_warnings:
            error_message = 'nSoft aktų dublikatų įspėjimai:\n\n' + duplicate_warnings
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            database = self._cr.dbname
            subject = '{} // [{}]'.format('nSoft Aktų dublikatai', database)
            self.env['script'].send_email(emails_to=[findir_email],
                                          subject=subject,
                                          body=error_message)

    @api.model
    def fetch_warehouses(self, cursor):
        """
        Fetch warehouses from external nSoft database
        :param cursor: nsoft cursor
        :return: List of warehouse IDs [12, 123, ...]
        """
        warehouse_query = """
            SELECT sand_id AS warehouse_id FROM view_sandeliai
            """
        # Default values taken from nSoft function that is simulated here
        result_data = []

        # Execute the query and fetch the results
        cursor.execute(warehouse_query)
        data = cursor.fetchall()

        # Group the data
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]
        for record in records:
            warehouse_id = record.get('warehouse_id')
            # if values are not none, fetch them to the dict
            if warehouse_id:
                result_data.append(warehouse_id)
        return result_data

    @api.model
    def fetch_base_report_data(self, cursor, date_from, doc_types):
        """
        Fetch the base data (IDs, dates...) of nSoft reports,
        lines are fetched separately
        :param cursor: nSoft DBs' SQL Cursor object
        :param date_from: report.date.from
        :param doc_types: report document types
        :return: Report data in list of dicts [{}, ...]
        """
        las_report_query = """
            SELECT
            dok_id AS doc_id, dok_data AS doc_date, 
            dok_tipas AS doc_type, dok_laikas AS ext_create_date, dok_kodas AS ext_doc_number
            FROM b_dok
            WHERE b_dok.dok_data >= %(doc_date)s
            AND dok_tipas in %(doc_types)s
            ORDER BY dok_data DESC;
        """
        # Default values taken from nSoft function that is simulated here
        result_data = []

        # Execute the query and fetch the results
        cursor.execute(las_report_query, {'doc_date': date_from, 'doc_types': tuple(doc_types)})
        data = cursor.fetchall()

        # Group the data
        header = [col[0] for col in cursor.description]
        records = [dict(zip(header, x)) for x in data]
        for record in records:
            doc_id = record.get('doc_id')
            # if values are not none, fetch them to the dict
            if doc_id:
                result_data.append({
                    'doc_id': doc_id,
                    'doc_date': record.get('doc_date'),
                    'doc_type': record.get('doc_type'),
                    'ext_create_date': record.get('ext_create_date'),
                    'ext_doc_number': record.get('ext_doc_number'),
                })
        return result_data

    @api.model
    def get_main_sum_report_query(self):
        """
        Main document query taken from nSoft database (with minimal adjustments)
        Moved to separate method for clarity. Used to fetch the lines for
        each report using it's external ID
        :return: query (str)
        """
        query = """
              SELECT sandelis.sub_id AS warehouse_id, sandelis.sub_pavarde AS warehouse_name, 
              b_preke.prek_id AS product_id, b_preke.prek_kodAS AS product_code, 
                    kategorija.prek_id AS category_id, kategorija.prek_pavadinimAS AS category_name,
                    b_preke.prek_pavadinimas AS product_name, b_mato_vienetai.mvnt_trumpinys AS uom_name,
                    SUM(start_qty) AS start_qty,
                    SUM(start_amount) AS start_amount,
                    SUM(inc_qty) AS inc_qty,
                    SUM(inc_amount) AS inc_amount,
                    SUM(moved_qty) AS moved_qty,
                    SUM(moved_amt) AS moved_amt,
                    SUM(produced_qty) AS produced_qty,
                    SUM(produced_amount) AS produced_amount,
                    SUM(sold_qty) AS sold_qty,
                    SUM(sold_amount) AS sold_amount,
                    SUM(writeoff_qty) AS writeoff_qty,
                    SUM(writeoff_amount) AS writeoff_amount,
                    SUM(inv_qty) AS inv_qty,
                    SUM(inv_amount) AS inv_amount,
                    SUM(cred_qty) AS cred_qty,
                    SUM(cred_amount) AS cred_amount,
                    SUM(final_qty) AS final_qty,
                    SUM(final_amount) AS final_amount,
                    sub_padalinys AS sandelio_padalinys 
                  FROM (
                    SELECT prd_sandelis AS sandelis, prd_preke AS preke,
                       SUM( CASE when dok_data < %(date_from)s then prd_kiekis else 0 end ) AS start_qty, 
                       SUM( CASE when dok_data < %(date_from)s then savikaina else 0 end) AS start_amount,     

                       SUM( CASE when dok_tipAS =  3 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS inc_qty, 
                       SUM( CASE when dok_tipAS =  3 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_SUMa_bm else 0 end) AS inc_amount,

                       SUM( CASE when dok_tipAS =  1 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS moved_qty, 
                       SUM( CASE when dok_tipAS =  1 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then savikaina else 0 end) AS moved_amt,

                       SUM( CASE when dok_tipAS =  4 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS produced_qty, 
                       SUM( CASE when dok_tipAS =  4 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then savikaina else 0 end) AS produced_amount,

                       SUM( CASE when dok_tipAS IN (2,5) AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS sold_qty, 
                       SUM( CASE when dok_tipAS IN (2,5) AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then savikaina else 0 end) AS sold_amount,

                       SUM( CASE when dok_tipAS =  7 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS writeoff_qty, 
                       SUM( CASE when dok_tipAS =  7 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then savikaina else 0 end) AS writeoff_amount,

                       SUM( CASE when dok_tipAS =  6 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS inv_qty, 
                       SUM( CASE when dok_tipAS =  6 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then savikaina else 0 end) AS inv_amount,

                       SUM( CASE when dok_tipAS =  8 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_kiekis else 0 end ) AS cred_qty, 
                       SUM( CASE when dok_tipAS =  8 AND dok_data >= %(date_from)s AND dok_data <= %(date_to)s 
                       then prd_SUMa_bm else 0 end) AS cred_amount,

                       SUM( CASE when dok_data <= %(date_to)s then prd_kiekis else 0 end ) AS final_qty, 
                       SUM( CASE when dok_data <= %(date_to)s then savikaina else 0 end) AS final_amount 

                     FROM ( SELECT prd_id, dok_id, dok_data, dok_tipAS, prd_sandelis, 
                     prd_preke, prd_kiekis, prd_suma_bm, sign(prd_kiekis) * SUM(prl_suma) AS savikaina
                           FROM b_perkelimai_detail 
                             JOIN b_dok on prd_dok = dok_id 
                             LEFT JOIN b_perkelimai_log ON prl_prd_id = prd_id
                             LEFT JOIN b_preke AS preke ON prd_preke = prek_id
                           WHERE dok_data >= %(date_from)s AND prd_statusas = 1 
                           AND prd_sandelis in %(warehouse_ids)s
                           AND dok_id = %(doc_id)s
                           GROUP BY prd_id, dok_id, dok_data, dok_tipAS, 
                           prd_sandelis, prd_preke, prd_kiekis, prd_suma_bm) AS pekelimai 
                     GROUP BY prd_sandelis, prd_preke, dok_id
                     UNION ALL   
                     SELECT dsz_sandelis, dsz_preke,
                       dsz_kiekis AS start_qty,
                       dsz_suma AS start_amount,
                       0 AS inc_qty,
                       0 AS inc_amount,
                       0 AS moved_qty,
                       0 AS moved_amt,
                       0 AS produced_qty,
                       0 AS produced_amount,
                       0 AS sold_qty,
                       0 AS sold_amount,
                       0 AS writeoff_qty,
                       0 AS writeoff_amount,
                       0 AS inv_qty,
                       0 AS inv_amount,
                       0 AS cred_qty,
                       0 AS cred_amount,
                       dsz_kiekis AS final_qty,
                       dsz_SUMa AS final_amount  
                     FROM b_dok_sandelio_zaliavos WHERE dsz_uzdarymas = %(doc_id)s 
                     AND dsz_sandelis in %(warehouse_ids)s) AS qq
                    JOIN subjektAS AS sandelis on sandelis.sub_id = qq.sandelis
                    JOIN b_preke on prek_id = qq.preke
                    JOIN b_mato_vienetai on mvnt_id = prek_matovnt
                    LEFT JOIN ( SELECT pgr_preke, prek_id, prek_pavadinimas FROM b_prekiu_grupe  
                                      JOIN b_preke AS kategorija ON (pgr_grupe = kategorija.prek_id 
                                      AND kategorija.prek_tipas = 6)) AS kategorija 
                                      ON (b_preke.prek_id = kategorija.pgr_preke)
                  GROUP by sandelis.sub_id, sandelis.sub_pavarde, b_preke.prek_id, b_preke.prek_kodAS, 
                  kategorija.prek_id, kategorija.prek_pavadinimas, 
                  b_preke.prek_pavadinimas, b_mato_vienetai.mvnt_trumpinys
                  ORDER by b_preke.prek_kodas, b_preke.prek_pavadinimas;
            """
        return query

    # Cron-Jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_recreate_fetched_data(self):
        """
        Cron-job that re-creates/re-confirms failed or not yet created nSoft data.
        Data from quantitative and sum accounting is included in this process.
        :return: None
        """

        # Ref needed objects
        NsoftSaleLine = self.env['nsoft.sale.line'].sudo()
        NsoftInvoice = self.env['nsoft.invoice'].sudo()

        # Get accounting lock date
        lock_date = self.sudo().env.user.company_id.get_user_accounting_lock_date()

        # Reconfirm stock pickings ---------------------------------------------------------------------------------
        domain = [('external_invoice', '=', True),
                  ('picking_id.state', 'in', ['confirmed', 'assigned', 'partially_available'])]
        # If lock date exists, append it to the domain
        if lock_date:
            domain.append(('date_invoice', '>', lock_date))

        # Search for external invoices that have a non-transferred picking
        picking_invoices = self.env['account.invoice'].search(domain)
        picking_invoices.confirm_related_pickings()

        # Re-create failed nSoft invoices/sales -- Correct invoices ------------------------------------------------
        sale_domain = [('invoice_id', '=', False), ('state', '!=', 'created')]
        invoice_domain = [('sale_line_ids.invoice_id', '=', False)] + sale_domain
        if lock_date:
            sale_domain.append(('sale_date', '>', lock_date))
            invoice_domain.append(('date_invoice', '>', lock_date))
        nsoft_sale_lines = NsoftSaleLine.search(sale_domain)
        nsoft_invoices = NsoftInvoice.search(invoice_domain)

        NsoftSaleLine.invoice_creation_prep(sale_line_ids=nsoft_sale_lines, nsoft_invoice_ids=nsoft_invoices)
        NsoftInvoice.create_correction_invoices()
        NsoftInvoice.spec_invoice_creation_preprocess()
        self.env['nsoft.payment'].re_reconcile()

        # Re-create sum accounting data ---------------------------------------------------------------------------
        company = self.sudo().env.user.company_id
        if company.nsoft_accounting_type and company.nsoft_accounting_type == 'sum':

            # Build domains
            report_move_domain = [('state', '!=', 'created')]
            purchase_domain = report_move_domain[:] + [('invoice_id', '=', False)]

            # If lock date exists, add date checks to domains
            if lock_date:
                report_move_domain.append(('report_date', '>', lock_date))
                purchase_domain.append(('date_invoice', '>', lock_date))

            # Search for the records
            report_moves = self.env['nsoft.report.move'].search(report_move_domain)
            purchase_invoices = self.env['nsoft.purchase.invoice'].search(purchase_domain)

            report_moves.move_creation_prep()
            purchase_invoices.purchase_invoice_creation_prep()

        if company.enable_nsoft_cash_operations:
            # Recreate nsoft cash operations
            cash_ops = self.env['nsoft.cash.operation'].search(
                [('payment_id', '=', False), ('state', '!=', 'created')]
            )
            cash_ops.create_account_payments_prep()

    @api.model
    def cron_fetch_base_data(self):
        """
        Fetches data for all nsoft objects from external database,
        creates external records and proceeds with corresponding systemic record creation.
        :return: None
        """

        cursor = self.get_external_cursor()
        # Check if connection was made
        if not cursor:
            return

        company = self.env.user.company_id
        # If it's weekend, fetch data for the whole week, otherwise use 2-day interval on fetching.
        sync_date = company.last_nsoft_db_sync
        if sync_date:
            delta = 7 if datetime.now().weekday() == 5 else 1
            sync_date_dt = datetime.strptime(
                sync_date, tools.DEFAULT_SERVER_DATETIME_FORMAT) - relativedelta(days=delta)
            sync_date = sync_date_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        # Fetch base data - invoices and sale lines
        self.fetch_invoices(cursor, sync_date)
        self.fetch_sale_lines(cursor, sync_date)

        # Fetch cash operations
        self.fetch_cash_operation_data(cursor, sync_date)

        # Fetch sum accounting data
        self.fetch_create_sum_accounting()

        # Update last database synchronization date
        company.write({'last_nsoft_db_sync': datetime.now()})
        self.env.cr.commit()

        # Context that is meant to be passed from script
        if not self._context.get('skip_robo_record_creation'):
            self.cron_recreate_fetched_data()

    @api.model
    def cron_fetch_create_sum_accounting(self):
        """
        Cron job that acts as an intermediary method and calls base sum accounting fetchers.
        This cron is disabled by default and only used for testing purposes.
        """
        self.fetch_create_sum_accounting()

    # Misc Methods ----------------------------------------------------------------------------------------------------

    @api.model
    def get_external_cursor(self):
        """
        Connect to external nSoft database and return active cursor
        :return: psycopg2 cursor object / None
        """

        cursor = None
        IrConfigParameter = self.sudo().env['ir.config_parameter']

        # Try to get the config parameters
        host = IrConfigParameter.get_param('nsoft_host', str()).strip()
        db = IrConfigParameter.get_param('nsoft_db', str()).strip()
        user = IrConfigParameter.get_param('nsoft_user', str()).strip()
        password = IrConfigParameter.get_param('nsoft_password', str()).strip()
        port = IrConfigParameter.get_param('nsoft_port', str()).strip()

        # If at least one parameter is missing - don't try to connect
        if not host or not db or not user or not password or not port:
            return cursor

        try:
            conn = psycopg2.connect(
                dbname=db,
                user=user,
                host=host,
                password=password,
                port=port,
            )
        except Exception as e:
            self.send_bug(body='nSoft DB Connection Error - %s' % e.args[0])
            return cursor

        cursor = conn.cursor()
        return cursor

    @api.model
    def send_bug(self, body):
        """
        Send bug report to IT support
        :param body: bug body (str)
        :return: None
        """
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': 'nSoft sąskaitos importavimo įspėjimai [%s]' % self._cr.dbname,
            'error_message': body,
        })
