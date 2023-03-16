# -*- coding: utf-8 -*-
from odoo import models, api, _, exceptions, tools
from odoo.addons.queue_job.job import identity_exact
from six import iteritems
from ... import r_keeper_tools as rkt
from datetime import datetime
from lxml import etree
from xlrd import XLRDError
import logging
import pytz
import xlrd
import os

_logger = logging.getLogger(__name__)


class RKeeperDataImport(models.AbstractModel):
    _name = 'r.keeper.data.import'
    _description = '''
    Abstract model that is used to parse
    rKeeper XML files and our XLS files
    that are used for data import
    '''

    def get_channel_to_use(self, channel, operation_type):
        """ Return the channel to use for given operation
        param channel: index of subchannel to use
        param operation_type: one of  'invoice', 'production_prep', 'reservation', 'confirm_stock_moves', 'payment'
        """
        operation_to_channel_mapping = {
            'invoice': ['root.single_1'],
            'payment': ['root.single_1'],
            'production_prep': ['root.single_1', 'root.single_2'],
            'reservation': ['root.single_3', 'root.single_4', 'root.single_5', 'root.single_6'],
            'confirm_stock_moves': ['root.single_7', 'root.single_8', 'root.single_9'],
        }
        n_channels = int(self.env['ir.config_parameter'].get_param('rkeeper_job_channels') or 1)
        channels = operation_to_channel_mapping.get(operation_type, ['root.single_10'])
        return channels[channel % min(n_channels, len(channels))]

    # XML Processors --------------------------------------------------------------------------------------------------

    @api.model
    def parse_xml_file(self, xml_data):
        """
        Method that prepares creation of records using passed XML data.
        Method is separated from the wizard to maintain autonomy.
        :param xml_data: XML data in string format
        :return: dict of parsed data (payments, sales)
        """

        def parse_node(node, date=False):
            """Parse text of passed XML node"""
            if node is not None:
                return node.text.replace('.', '-') if date else node.text
            return None

        try:
            root = etree.fromstring(unicode(xml_data, errors='ignore'))
        except Exception as exc:
            raise exceptions.ValidationError(
                _('rKeeper XML apdorojimas: Netinkamas failo formatas. Klaida %s') % exc.args[0]
            )

        # Get accounting threshold date, if it's not set, return
        configuration = self.env['r.keeper.configuration'].get_configuration()
        th_date = configuration.accounting_threshold_date
        if not th_date:
            return
        th_date_dt = datetime.strptime(th_date, tools.DEFAULT_SERVER_DATE_FORMAT)

        # Check operation type
        operation_type = parse_node(root.find('I06_OP_TIP'))
        if operation_type != '53':
            raise exceptions.ValidationError(_('rKeeper XML apdorojimas: Gauta ne pardavimo operacija'))

        # Get batch document number
        doc_number = parse_node(root.find('I06_DOK_NR'))
        if not doc_number:
            doc_number = parse_node(root.find('I06_DOK_REG'))
            if not doc_number:
                raise exceptions.ValidationError(_('rKeeper XML apdorojimas: Nepaduodas dokumento numeris'))

        # Get dates
        operation_date = parse_node(root.find('I06_OP_DATA'), date=True)
        doc_date = parse_node(root.find('I06_DOK_DATA'), date=True)

        if not doc_date:
            raise exceptions.ValidationError(_('rKeeper XML apdorojimas: Nerasta pardavimo data'))

        # Do not parse entries earlier than threshold date
        doc_date_dt = datetime.strptime(doc_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        if doc_date_dt < th_date_dt:
            return

        # Get other extra information
        pos_code = parse_node(root.find('I06_KODAS_KS'))

        # Weird syntax, i know, payment is completed if value is 2.0
        payment_completed = float(parse_node(root.find('I06_MOK_SUMA'))) == 2.0
        extra_data = parse_node(root.find('I06_PASTABOS'))

        # Get sale and payment blocks
        payment_blocks = root.findall('.//I13')
        sale_blocks = root.findall('.//I07')
        modifier_blocks = root.findall('.//I08')

        force_update_amounts = self._context.get('force_update_amounts')
        # Loop through sale blocks and parse them
        sales = []
        for sale in sale_blocks:
            line_pos_code = parse_node(sale.find('I07_KODAS_IS'))

            # If global pos code does not match line pos code, raise an error
            if pos_code != line_pos_code:
                raise exceptions.ValidationError(
                    _('rKeeper XML apdorojimas: Eilutės POS kodas neatitinka globalaus POS kodo'))

            # Get product code if it does not exist, raise an error
            product_code = parse_node(sale.find('I07_KODAS'))
            if not product_code:
                product_code = parse_node(sale.find('DI07_BAR_KODAS'))
                if not product_code:
                    raise exceptions.ValidationError(
                        _('rKeeper XML apdorojimas: Produkto kodas neegzistuoja'))

            product_quantity = float(parse_node(sale.find('T_KIEKIS')))
            pos_code = parse_node(sale.find('I07_KODAS_IS'))

            # No other way to check for uniqueness
            potential_duplicate = self.env['r.keeper.sale.line'].search(
                [('doc_number', '=', doc_number),
                 ('product_code', '=', product_code),
                 ('pos_code', '=', pos_code)], limit=1)

            potential_duplicate = potential_duplicate.filtered(
                lambda x: not tools.float_compare(x.quantity, product_quantity, precision_digits=2)
            )
            # Get potential duplicate batch, and filter out again by amount
            if potential_duplicate:
                # Skip the duplicates. On update mode, check the amounts beforehand
                if force_update_amounts:
                    # Get sale amounts
                    amount_data = {
                        'pu_wo_vat': float(parse_node(sale.find('I07_KAINA_BE'))),
                        'pu_w_vat': float(parse_node(sale.find('I07_KAINA_SU'))),
                        'amount_vat': float(parse_node(sale.find('I07_PVM'))),
                        'amount_wo_vat': float(parse_node(sale.find('I07_SUMA'))),
                    }
                    data_changes = {}
                    for field, value in amount_data.items():
                        # Collect the amount differences
                        if tools.float_compare(potential_duplicate[field], value, precision_digits=2):
                            data_changes[field] = value

                    # Write the differences (if any) and update the state
                    if data_changes:
                        data_changes.update({'state': 'updated'})
                        potential_duplicate.write(data_changes)
                continue

            # rKeeper sale line data is prepared
            sale_data = {
                'doc_number': doc_number,
                'sale_date': operation_date,
                'doc_date': doc_date,
                'extra_data': extra_data,
                'product_type': parse_node(sale.find('I07_TIPAS')),
                'product_code': product_code,
                'product_name': parse_node(sale.find('I07_PAV')),
                'uom_code': parse_node(sale.find('I07_KODAS_US_A')),
                'pos_code': pos_code,
                'quantity': product_quantity,
                'pu_wo_vat': float(parse_node(sale.find('I07_KAINA_BE'))),
                'pu_w_vat': float(parse_node(sale.find('I07_KAINA_SU'))),
                'amount_vat': float(parse_node(sale.find('I07_PVM'))),
                'amount_wo_vat': float(parse_node(sale.find('I07_SUMA'))),
                'payment_completed': payment_completed,
            }
            sales.append(sale_data)

        # Loop through payment blocks and parse them
        payments = []
        for payment in payment_blocks:
            # rKeeper payment data is prepare

            # Get values that are used in duplicate checking
            payment_type_code = parse_node(payment.find('I13_KODAS_SS'))
            payment_amount = float(parse_node(payment.find('I13_SUMA')))

            # No other way to check for uniqueness, since there's no ID per line
            potential_duplicates = self.env['r.keeper.payment'].search(
                [('doc_number', '=', doc_number),
                 ('pos_code', '=', pos_code),
                 ('payment_type_code', '=', payment_type_code)])

            # Get potential duplicate batch, and filter out again by amount
            if potential_duplicates.filtered(lambda x: not tools.float_compare(
                    x.amount, payment_amount, precision_digits=2)):
                continue

            # Prepare payment data
            payment_data = {
                'doc_number': doc_number,
                'payment_date': operation_date,
                'doc_date': doc_date,
                'pos_code': pos_code,
                'extra_data': extra_data,
                'payment_type_code': payment_type_code,
                'amount': payment_amount,
            }
            payments.append(payment_data)

        # Loop modifier blocks and parse them
        ungrouped_modifiers = []
        for modifier in modifier_blocks:
            # rKeeper payment data is prepare

            # Get values that are used in duplicate checking
            modifier_code = parse_node(modifier.find('I08_KODAS'))
            modifier_name = parse_node(modifier.find('I08_PAV'))
            modified_product_code = parse_node(modifier.find('I08_KODAS_PAT'))
            quantity = float(parse_node(modifier.find('T_KIEKIS')))

            # Check for actual modifier record
            r_keeper_modifier = self.env['r.keeper.modifier'].search(
                [('modifier_code', '=', modifier_code), ('product_code', '=', modified_product_code)])
            if not r_keeper_modifier:
                r_keeper_modifier = self.env['r.keeper.modifier'].create({
                    'modifier_code': modifier_code,
                    'modifier_name': modifier_name,
                    'product_code': modified_product_code,
                })

            # Check for sale line modifier duplicates
            potential_duplicates = self.env['r.keeper.sale.line.modifier'].search(
                [('doc_number', '=', doc_number),
                 ('r_keeper_modifier_id', '=', r_keeper_modifier.id),
                 ('modifier_code', '=', modifier_code),
                 ('pos_code', '=', pos_code),
                 ('product_code', '=', modified_product_code)])

            # Get potential duplicate batch, and filter out again by quantity
            if potential_duplicates.filtered(lambda x: not tools.float_compare(
                    x.modified_quantity, quantity, precision_digits=2)):
                continue

            # Prepare modifier data
            modifier_data = {
                'doc_date': doc_date,
                'doc_number': doc_number,
                'product_code': modified_product_code,
                'modifier_code': modifier_code,
                'pos_code': pos_code,
                'modified_quantity': quantity,
                'r_keeper_modifier_id': r_keeper_modifier.id,
            }
            ungrouped_modifiers.append(modifier_data)

        # Aggregate modifiers by ID
        grouped_modifiers = {}
        for modifier in ungrouped_modifiers:
            mod_id = modifier['r_keeper_modifier_id']
            # Add the quantity if it's already in the batch
            if mod_id in grouped_modifiers:
                grouped_modifiers[mod_id]['modified_quantity'] += modifier['modified_quantity']
            else:
                grouped_modifiers[mod_id] = modifier
        modifiers = grouped_modifiers.values()

        return {
            'parsed_payments': payments,
            'parsed_sales': sales,
            'parsed_modifiers': modifiers,
        }

    @api.model
    def create_records_from_xml(self, data_sets, commit_after_each=False):
        """
        Creates rKeeper payments and sales, based on passed data.
        :param data_sets: dict with 'parsed_payments' and/or
               'parsed_sales' blocks. Data must be processed in
               a way to fit instant record creation
        :param commit_after_each: Boolean flag, indicates
               whether commit must be made after each loop
        :return: None
        """
        payments = data_sets.get('parsed_payments')
        sales = data_sets.get('parsed_sales')
        modifiers = data_sets.get('parsed_modifiers')

        # Commit after each should be used in rare/edge cases
        # since, individual objects do not have ID, just the
        # whole batch, that's why, we either create all or None

        # Create payments
        for payment in payments:
            self.env['r.keeper.payment'].create(payment)
            if commit_after_each:
                self.env.cr.commit()

        # Create sales
        for sale in sales:
            self.env['r.keeper.sale.line'].create(sale)
            if commit_after_each:
                self.env.cr.commit()

        # Create sales
        for modifier in modifiers:
            self.env['r.keeper.sale.line.modifier'].create(modifier)
            if commit_after_each:
                self.env.cr.commit()

    # XLS Processors --------------------------------------------------------------------------------------------------

    @api.model
    def parse_xls_file(self, xls_data, file_type):
        """
        Method that prepares creation of records using passed XML data.
        Method is separated from the wizard to maintain autonomy.
        :param xls_data: XLS data in string format
        :param file_type: XLS file type in string format
        :return: dict of parsed data (payments, sales)
        """

        # Load up the file in workbook
        try:
            wb = xlrd.open_workbook(file_contents=xls_data)
        except XLRDError:
            raise exceptions.ValidationError(_('rKeeper XLS apdorojimas: Netinkamas failo formatas'))
        sheet = wb.sheets()[0]

        # Get the field list of the file
        field_lists = rkt.XLS_FIELD_LIST_MAPPING.get(file_type)
        if not field_lists:
            raise exceptions.ValidationError(_('rKeeper XLS apdorojimas: Netinkamas failo tipas'))

        data_set = []
        # Loop through sheet rows
        for row in range(sheet.nrows):
            if row == 0:
                continue
            col = 0
            record = {'row_number': str(row + 1)}
            # Loop through columns and parse values
            for field in field_lists['all_fields']:
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = False
                # Try to convert code to int and to str
                # since all numbered codes get
                # this format 123456.0
                if field == 'code':
                    try:
                        value = str(int(value))
                    except ValueError:
                        pass
                if field in field_lists['boolean_fields']:
                    # XLS file has protected values in the list selection,
                    # thus string is eiter exactly 'TRUE' or 'FALSE'
                    value = True if value == 'TRUE' else False

                # If field is in required fields and value is False-able, raise an error
                if field in field_lists['required_fields'] and not value and not isinstance(value, (int, float)):
                    raise exceptions.ValidationError(
                        _('rKeeper XLS parsing: No value was given for required field - %s. Row number - %s') % (
                            field, str(row + 1))
                    )
                record[field] = value
                col += 1
            # Append data to dataset
            data_set.append(record)
        return data_set

    @api.model
    def create_records_from_xls(self, data_set, file_type):
        """
        Creates rKeeper payments and sales, based on passed data.
        :param data_set: List of records based on file_type
        :param file_type: Indicates which type of records are passed
        :return: None
        """

        if file_type == 'payment_type_xls':
            for data in data_set:
                # Check passed journal type
                journal_type = data.get('journal_type', 'sale')
                if journal_type not in rkt.ALLOWED_PAYMENT_JOURNAL_TYPES:
                    raise exceptions.ValidationError(
                        _('rKeeper XLS aodorojimas: Netinkamas žurnalo tipas. Galimi tipai %s') %
                        rkt.ALLOWED_PAYMENT_JOURNAL_TYPES
                    )

                # Create journal
                name = 'rKeeper: {}'.format(data['name'])
                journal = self.env['account.journal'].create({
                    'name': name,
                    'code': 'RKP{}'.format(data['code'][:6]),
                    'type': journal_type
                })
                # If journal type is not cash, create accounts
                if journal_type != 'cash':
                    # Check passed account type
                    account_type = data.get('account_type', 'receivable')
                    if account_type not in rkt.ALLOWED_PAYMENT_ACCOUNT_TYPES:
                        raise exceptions.ValidationError(
                            _('rKeeper XLS aodorojimas: Netinkamas buh. sąskaitos tipas. Galimi tipai %s') %
                            rkt.ALLOWED_PAYMENT_ACCOUNT_TYPES
                        )
                    account_type_id = self.env.ref(rkt.ACCOUNT_TYPE_MAPPING[account_type])
                    # Create the account
                    account_code_prefix = '241'
                    for num in range(1, 10):
                        new_code = '{}{}'.format(account_code_prefix, num)
                        if not self.env['account.account'].with_context(
                                active_test=False).search_count([('code', '=', new_code)]):
                            successful_check, parent_code = self.env['account.account'].is_parent_can_become_view(
                                new_code, self.env.user.company_id.id)
                            if successful_check:
                                break
                    else:
                        # If there are no free codes, raise an error
                        raise exceptions.ValidationError(
                            _('rKeeper XLS aodorojimas: Nepavyko sukurti mokėjimo tipo, nebėra laisvų kodų')
                        )
                    account = self.env['account.account'].create({
                        'name': name,
                        'code': new_code,
                        'reconcile': data['reconcilable_account'],
                        'user_type_id': account_type_id.id,
                    })
                    # Write the code to the journal
                    journal.write({
                        'default_debit_account_id': account.id,
                        'default_credit_account_id': account.id
                    })

                # Create the record
                self.env['r.keeper.payment.type'].create({
                    'name': data['name'],
                    'code': data['code'],
                    'journal_id': journal.id,
                })

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_fetch_r_keeper_data(self):
        """
        Cron //
        Fetches data from rKeeper servers
        :return: None
        """
        # Check rKeeper integration (Only partially, records are fetched every day)
        if not self.env['r.keeper.configuration'].check_r_keeper_configuration(partial_check=True):
            return

        # Initiate SSH connection
        rk_ssh_obj = self.env['r.keeper.ssh.connector']
        ssh_conn = rk_ssh_obj.initiate_r_keeper_connection()

        # Open SFTP connection
        sftp_object = ssh_conn.open_sftp()

        # Get external directory names
        dirs = rk_ssh_obj.get_r_keeper_directories(sftp_object=sftp_object)

        fetched_imports = rKeeperDataImportJob = self.env['r.keeper.data.import.job']
        # Get the file names that we need to import
        std_in, std_out, std_err = ssh_conn.exec_command('dir {} /b'.format(
            dirs['ult_export_dir'])
        )
        # If we get error, log it and raise an exception
        if std_err.readlines():
            raise exceptions.ValidationError(_('rKeeper: Nepavyko surinkti nuotolinių importo failų.'))

        file_names = []
        # Loop through ssh response and gather file_names
        for file_name in std_out.readlines():
            sanitized_name = file_name.strip()
            # Once again check for the file extension
            if rkt.FETCHED_FILE_EXTENSION in sanitized_name:
                file_names.append(sanitized_name)

        # Loop through the file names and download them
        if file_names:
            for file_name in file_names:
                ult_remote_file_path = '{}\\{}'.format(dirs['ult_export_dir'], file_name)
                ult_local_file_path = '{}/{}'.format(dirs['local_temp_dir'], file_name)

                # Workarounds due to rKeeper folders with spaces
                ult_remote_file_path = ult_remote_file_path.replace('"', '')

                # Fetch the file via SFTP
                sftp_object.get(ult_remote_file_path, ult_local_file_path)

                # Read fetched file
                with open(ult_local_file_path, 'rb') as f:
                    file_data = f.read().encode('base64')
                    if file_data:
                        # Create import job object
                        fetched_imports |= fetched_imports.create({
                            'imported_api': True,
                            'imported_file_name': file_name,
                            'imported_file': file_data
                        })
                # Delete the file locally
                os.remove(ult_local_file_path)

                # Move the file to processed export directory in external server
                std_in, std_out, std_err = ssh_conn.exec_command('move "{}" {}'.format(
                    ult_remote_file_path, dirs['ult_proc_export_dir'])
                )
                # If we get error, log it and raise an exception
                if std_err.readlines():
                    raise exceptions.ValidationError(
                        _('rKeeper: Nepavyko perkelti nuotlinių importo failų į apdorotų failų direktoriją')
                    )
            # Close SFTP object
            sftp_object.close()
        # Close SSH connection and commit fetched files
        ssh_conn.close()
        self.env.cr.commit()
        # Get all of the other failed/non processed imports and parse them along with the fetched files
        fetched_imports |= rKeeperDataImportJob.search([('state', 'in', ['failed', 'no_action'])])
        self.parse_imported_files(forced_jobs=fetched_imports)

    @api.model
    def parse_imported_files(self, forced_jobs=None):
        """
        Parses API imported rKeeper XML/EIP files
        :return: None
        """
        # Gather import jobs to parse
        if forced_jobs is not None:
            import_jobs = forced_jobs
        else:
            import_jobs = self.env['r.keeper.data.import.job'].search(
                [('imported_api', '=', True),
                 ('state', 'in', ['no_action', 'failed']),
                 ('file_type', '=', 'sale_xml')]
            )
        # Loop through them and parse the files
        for import_job in import_jobs:
            import_job.parse_xml_file_prep()

    @api.model
    def cron_process_imported_data(self, picking_limit=300):
        """
        Cron //
        Processes rKeeper data (payments, sales)
        and creates system records - invoices, moves
        :param picking_limit: Limit of the pickings to be confirmed
        :return: None
        """
        # Check rKeeper integration (Fully, records are created based on setting)
        if not self.env['r.keeper.configuration'].check_r_keeper_configuration():
            return

        sale_obj = self.env['r.keeper.sale.line'].sudo()
        payment_obj = self.env['r.keeper.payment'].sudo()

        # Recalculate BOMs at date for the sales
        _logger.info('rKeeper data processing: Recalculate BOM at date')
        sale_obj.calculate_has_bom_at_date()
        _logger.info('rKeeper data processing: Recalculate BOM at date -- Done')

        # Create invoices from sale lines
        sales_to_invoice = sale_obj.search(
            [('invoice_id', '=', False),
             ('zero_amount_sale', '=', False),
             ('state', 'in', ['imported', 'failed'])]
        )
        if sales_to_invoice:
            sales_to_invoice.create_invoices_prep()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Create invoices -- Done')

        base_zero_sale_domain = [
            ('inventory_id', '=', False), ('zero_amount_sale', '=', True),
            ('state', 'in', ['imported', 'failed_inventory', 'failed'])
        ]
        # Produce zero amount sales before creating related write-offs
        zero_sales_to_produce = sale_obj.search(
            base_zero_sale_domain + [('mrp_production_id', '=', False)]
        )
        if zero_sales_to_produce:
            zero_sales_to_produce.with_delay(
                channel=self.get_channel_to_use(1, 'production_prep'),
                identity_key=identity_exact,
                priority=90,
                description='Prepare rKeeper sale line objects for Mrp Production creation of zero amount sales',
                eta=30
            ).create_production_prep()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Producing zero amount sales -- Done')

        # See if there's any write-offs to create (skip all partial failed reservation states)
        sales_to_write_off = sale_obj.search(
            base_zero_sale_domain + [('production_state', 'in', ['produced', 'not_produced'])]
        )
        if sales_to_write_off:
            sales_to_write_off.create_inventory_write_off_prep()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Creating write-offs -- Done')

        # Create refund invoices from payments
        payments_to_refund = payment_obj.search(
            [('refund_invoice_id', '=', False),
             ('payment_type_id.create_refund_invoice', '=', True),
             ('refund_invoice_state', 'in', ['no_action', 'failed'])]
        )
        if payments_to_refund:
            payments_to_refund.create_refund_payment_invoice_prep()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Creating refund invoices from payments -- Done')

        # Create moves from payments
        payments_to_create = payment_obj.search(
            [('move_id', '=', False),
             ('state', 'in', ['active', 'warning', 'failed'])]
        )
        if payments_to_create:
            payments_to_create.create_account_moves_prep()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Creating payment account moves -- Done')

        # Gather other payments that can be reconciled
        payments_to_reconcile = payment_obj.search(
            ['|', '&',
             ('refund_invoice_id', '!=', False),
             ('refund_invoice_id.reconciled', '=', False),
             '&', '&',
             ('move_id', '!=', False),
             ('state', 'in', ['partially_reconciled', 'open']),
             ('payment_type_id.do_reconcile', '=', True)]
        )
        if payments_to_reconcile:
            payments_to_reconcile.with_delay(
                identity_key=identity_exact, description='Reconcile rKeeper payments',
                channel=self.env['r.keeper.data.import'].get_channel_to_use(1, 'payment'),
                priority=90).reconcile_payments()
        self.env.cr.commit()
        _logger.info('rKeeper data processing: Reconciling payments -- Done')

        # Check whether there are any pickings that need to be confirmed
        # All of the grouping and sorting is done in sql query
        self.env.cr.execute('''
            SELECT R1.picking_id FROM (
                SELECT picking_id FROM (
                    SELECT picking_id, RKS.production_state, SP.write_date 
                    FROM r_keeper_sale_line AS RKS 
                    INNER JOIN stock_picking AS SP ON RKS.picking_id = SP.id 
                    WHERE SP.state not in ('done', 'cancel')
                    GROUP BY picking_id, production_state, SP.write_date
                    ORDER BY SP.write_date ASC
                ) SUB GROUP BY picking_id HAVING COUNT(picking_id) = 1) R1
            INNER JOIN (
                SELECT DISTINCT picking_id FROM r_keeper_sale_line 
                WHERE production_state = 'produced' 
                AND picking_id IS NOT NULL
            ) R2 ON R1.picking_id = R2.picking_id LIMIT %s
        ''', (picking_limit, ))
        # Gather the picking IDs
        picking_ids = [pick[0] for pick in self.env.cr.fetchall() if pick]
        for picking_id in picking_ids:
            # Re-browse the pickings and try to confirm them
            picking = self.env['stock.picking'].browse(picking_id)
            if len(picking.move_lines) > 20:
                # Skip those with two many lines
                continue
            picking.with_delay(
                channel=self.get_channel_to_use(1, 'confirm_stock_move'),
                identity_key=identity_exact,
                priority=90,
                description='Confirm rKeeper picking',
                eta=30
            ).confirm_r_keeper_pickings()
        _logger.info('rKeeper data processing: Confirming pickings -- Done')

    @api.model
    def cron_produce_sales_small_batches(self, limit=30, skip_confirmation=False):
        """
        Cron job that gathers rKeeper sales that need their productions confirmed or created.
        Sales are grouped by points of sale, and then passed to queue job handling method
        :param limit: Record limit count (int)
        :param skip_confirmation: Indicates whether confirmation of already created
        productions should be skipped or not
        :return: None
        """
        # Run the cron from 03:00 till 19:00 every n minutes
        # (If needed configuration params might be added)
        current_hour = datetime.now(pytz.timezone('Europe/Vilnius')).hour
        if current_hour < 3 or current_hour > 18:
            return

        # Prepare the production data that is going to be passed to queue jobs
        production_data = self.prepare_production_job_data(
            production_limit=limit, skip_confirmation=skip_confirmation,
        )
        for pos, grouped_data in iteritems(production_data):
            self.confirm_production_sales_job(pos.id, grouped_data)

    @api.model
    def prepare_production_job_data(self, production_limit, skip_confirmation):
        """
        Method that groups sales production data by location
        into a format acceptable by queue job method
        :param production_limit: Record limit count (int)
        :param skip_confirmation: Indicates whether confirmation of already created
        productions should be skipped or not
        :return: Grouped production data (dict)
        """

        # Prepare needed objects
        rKeeperPointOfSale = self.env['r.keeper.point.of.sale'].sudo()
        rKeeperSaleLine = self.env['r.keeper.sale.line'].sudo()
        rKeeperConfiguration = self.env['r.keeper.configuration'].sudo()

        # Check whether resources should be split
        configuration = rKeeperConfiguration.get_configuration(raise_exception=False)
        split_resources = configuration.split_resources_between_new_production_creation_and_reservation

        # Get all working points of sale
        points_of_sale = rKeeperPointOfSale.search(
            [('location_id', '!=', False), ('journal_id', '!=', False), ('partner_id', '!=', False)]
        )
        production_data = {}
        # Loop through points of sales, and ensure that we take
        # same amount of productions (up to the limit) for each POS
        for point_of_sale in points_of_sale:
            sales_create_production = sales_confirm_production = rKeeperSaleLine
            # Gather the sales that need production confirmation
            if not skip_confirmation:
                domain = [
                    ('mrp_production_id', '!=', False),
                    ('point_of_sale_id', '=', point_of_sale.id),
                    ('mrp_production_id.state', 'not in', ['done', 'cancel']),
                ]
                doc_date_lim = self.env['ir.config_parameter'].sudo().get_param('rkeeper_doc_date_lim')
                if doc_date_lim:
                    domain.append(('doc_date', '<=', doc_date_lim))
                sales_confirm_production = rKeeperSaleLine.search(domain, limit=production_limit, order='write_date asc')

            if split_resources or not sales_confirm_production:
                creation_limit = production_limit
                # Only productions that are confirmable hit the limit ceiling
                # we diminish the creation limit by one third
                if len(sales_confirm_production) == production_limit:
                    creation_limit = creation_limit // 3
                domain = [
                    ('production_state', 'in', ['failed_to_create', 'not_produced']),
                    ('point_of_sale_id', '=', point_of_sale.id),
                    ('invoice_id', '!=', False),
                ]
                doc_date_lim = self.env['ir.config_parameter'].sudo().get_param('rkeeper_doc_date_lim')
                if doc_date_lim:
                    domain.append(('doc_date', '<=', doc_date_lim))

                sales_create_production = rKeeperSaleLine.search(domain, limit=creation_limit, order='write_date asc')

            # Setup two different batches - for confirmation, and creation
            if sales_confirm_production:
                production_data.setdefault(point_of_sale, {})
                production_data[point_of_sale].setdefault('confirm', rKeeperSaleLine)
                production_data[point_of_sale]['confirm'] |= sales_confirm_production

            if sales_create_production:
                production_data.setdefault(point_of_sale, {})
                production_data[point_of_sale].setdefault('create', rKeeperSaleLine)
                production_data[point_of_sale]['create'] |= sales_create_production

        return production_data

    @api.model
    def confirm_production_sales_job(self, channel, grouped_production_data):
        """
        Queue Job method that takes sales (grouped by location) and produces or confirms their productions
        :param channel: Queue job channel to use
        :param grouped_production_data: Production data that is grouped by points of sale and action
        :return: None
        """
        sales_to_confirm_pr = grouped_production_data.get('confirm', [])
        sales_to_create_pr = grouped_production_data.get('create', [])

        # Confirm passed sale productions
        for sale_line in sales_to_confirm_pr:
            sale_line.with_delay(
                channel=self.get_channel_to_use(channel, 'reservation'),
                identity_key=identity_exact,
                priority=90,
                description='Produce related rKeeper production (reservation)',
                eta=30
            )._produce_related_production()

        # Create passed sale productions
        for sale_line in sales_to_create_pr:
            sale_line.with_delay(
                channel=self.get_channel_to_use(channel, 'production_prep'),
                identity_key=identity_exact,
                priority=90,
                description='Prepare rKeeper sale line objects for Mrp Production creation',
                eta=30
            ).create_production_prep()
