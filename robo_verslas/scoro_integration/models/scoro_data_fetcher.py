# -*- coding: utf-8 -*-

from odoo import models, api, exceptions, _, tools
import requests
import json
from datetime import datetime
import pytz
import logging

_logger = logging.getLogger(__name__)
# todo's for the future: add bool in company settings that allows or denies product-less invoice creation


def validate_response(result):

    """Validate HTTP reponse and format the message;
        :param result - http response
        :return formatted message
     """

    code_mapper = {
        200: 200,
        400: 'This usually occurs because of a missing or malformed parameter. '
             'Check the documentation and the syntax of your request and try again.',
        401: 'A valid API key was not provided with the request, '
             'so the API could not associate a user with the request.',
        403: 'The API key was wrong.',
        408: 'The maximum execution time of the request was reached.',
        500: 'Problem on Scoro end.',
        503: 'API usage has been temporarily suspended. Try again later.'
    }
    static_message = code_mapper.get(result.get('statusCode', ''), '')
    dynamic_message = result.get('messages', '')
    data = result.get('data', False)
    response = str()
    if static_message and static_message != 200:
        response = 'Failed to fetch scoro data - Exception: {}. Extra text: {}'.format(static_message, dynamic_message)
    if not response and not data and static_message != 200:
        response = 'Failed to fetch scoro data - Unexpected error'
    return response


class ScoroDataFetcher(models.TransientModel):

    _name = 'scoro.data.fetcher'

    def get_request_template(self, filter_dict=None):

        """Get response template
        :param filter_dict specifies what filtering you want to add to API for specific objects
        lets assume invoice api has 'name' and 'date' fields. you can write
         'filter' : {
            'name': 'INV%',
            'date': {
                'from': '2019-01-01',
                'to': '2019-01-10'
            }
         }
         :return request_template
         """

        config_obj = self.sudo().env['ir.config_parameter']
        scoro_company_id = config_obj.get_param('scoro_company_account_id')
        scoro_api_key = config_obj.get_param('scoro_api_key')

        if not scoro_api_key:
            raise exceptions.Warning(_('Scoro API key is not configured!'))
        if not scoro_company_id:
            raise exceptions.Warning(_('Scoro company account ID is not configured!'))

        template = {
            'apiKey': scoro_api_key,
            'lang': 'eng',
            'company_account_id': scoro_company_id,
            'request': []
        }
        if filter_dict:
            template['filter'] = filter_dict
        return template

    def get_api(self, endpoint, object_id=''):

        """Return SCORO API request URL
            :param endpoint - api endpoint in scoro system
            :param object_id - id of object that needs to be accessed
            :return formatted message
         """
        endpoint_mapper = {
            'invoice_list': 'api/v2/invoices/list',
            'invoice_id':  '/api/v2/invoices/view/{}'.format(str(object_id)),
            'partner_list': '/api/v2/contacts/list',
            'partner_id': '/api/v2/contacts/view/{}'.format(str(object_id)),
            'product_list': '/api/v2/products/list',
            'product_id': '/api/v2/products/view/{}'.format(str(object_id)),
            'vat_code_list': '/api/v2/vatCodes/list'
        }

        config_obj = self.sudo().env['ir.config_parameter']
        scoro_company_name = config_obj.get_param('scoro_company_name')
        res = endpoint_mapper.get(endpoint, False)
        if not res:
            raise exceptions.Warning(_('Incorrect endpoint is passed!'))
        req_url = 'https://{}.scoro.lt/{}'.format(scoro_company_name, res)
        return req_url

    @api.model
    def create_res_partner(self, line):

        """Create res partner based on passed data from scoro system"""

        ResPartner = self.env['res.partner']
        contact_id = line.get('contact_id')
        name = line.get('name')
        code = line.get('id_code')
        contact_type = line.get('contact_type', 'company')
        if not contact_id or not name or (not code and contact_type in ['company']):
            return ResPartner

        partner = ResPartner.search([('scoro_external_id', '=', contact_id)])
        if partner:
            if partner.kodas != code:
                raise exceptions.ValidationError(
                    _('Received Scoro partner with duplicate external '
                      'ID [{}] but different code [{}]').format(contact_id, code)
                )
            return partner
        if code:
            partner = ResPartner.search([('kodas', '=', code)])
            if partner:
                partner.write({'scoro_external_id': contact_id})
                return partner

        bank_account = line.get('bankaccount')
        name_to_use = '{} {}'.format(name, line.get('lastname', '')) if contact_type in ['person'] else name
        partner_vals = {
            'name': name_to_use,
            'is_company': True if contact_type in ['company'] else False,
            'kodas': code,
            'vat': line.get('vatno', ''),
            'scoro_external_id': contact_id,
            'property_account_receivable_id': self.env['account.account'].sudo().search(
                [('code', '=', '2410')],
                limit=1).id,
            'property_account_payable_id': self.env['account.account'].sudo().search(
                [('code', '=', '4430')],
                limit=1).id,
        }
        try:
            partner_obj = ResPartner.create(partner_vals)
        except Exception as exc:
            exception = 'Scoro partner creation exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return ResPartner
        if bank_account:
            try:
                self.env['res.partner.bank'].create({'acc_number': bank_account, 'partner_id': partner_obj.id})
            except Exception as exc:
                _logger.info(exc.args)
        return partner_obj

    @api.model
    def create_product_product(self, line):
        # TODO: Maybe needed in the future if client company uses stock, not used ATM
        product_id = line.get('product_id')
        name = line.get('name')
        if not name or not product_id:
            return self.env['product.product']
        product_vals = {
            'name': name,
            'scoro_external_id': product_id,
            'acc_product_type': 'service',
            'type': 'service'
        }
        product_obj = self.env['product.product'].create(product_vals)
        return product_obj

    @api.model
    def create_scoro_tax(self, line):
        """
        Create scoro tax record
        :param line: scoro tax data
        :return: scoro.tax object
        """
        vat_code_id = line.get('vat_code_id')
        scoro_tax_id = self.env['scoro.tax'].search([('vat_code_id', '=', vat_code_id)])
        if scoro_tax_id:
            return self.env['scoro.tax']
        tax_vals = {
            'vat_name': line.get('vat_name', str()),
            'vat_code': line.get('vat_code', str()),
            'vat_code_id': line.get('vat_code_id'),
            'vat_percent': line.get('percent'),
            'vat_type': 'sale' if line.get('is_sales', False) else 'purchase'
        }
        scoro_tax_obj = self.env['scoro.tax'].create(tax_vals)
        return scoro_tax_obj

    @api.model
    def check_scoro_invoice(self, line, skip=True):
        """Check whether scoro_invoice exists in the system and check for changes"""
        report = str()
        external_id = line.get('id')
        # Check if external id is passed
        if external_id:
            scoro_invoice = self.env['scoro.invoice'].search([('external_id', '=', external_id)])
            if scoro_invoice:
                is_deleted = line.get('is_deleted', 0)
                if is_deleted and not scoro_invoice.is_deleted_scoro:
                    scoro_invoice.is_deleted_scoro = True
                elif not is_deleted:
                    report = self.collect_invoice_changes(scoro_invoice, line)
                    # If we receive a report of changed crucial fields
                    # Delete the system invoice and reset scoro invoice state
                    if report and scoro_invoice.invoice_id:
                        self.env.cr.commit()
                        try:
                            scoro_invoice.unlink_system_invoice()
                        except Exception as exc:
                            self.env.cr.rollback()
                            report += _(
                                'Nepavyko automatiškai atnaujinti sąskaitos. Klaidos pranešimas: %s'
                            ) % exc.args[0]
            # Keep return type consistency
            skip = bool(scoro_invoice)
        return skip, report

    @api.model
    def collect_invoice_changes(self, scoro_invoice, new_data):
        """Check for changes between system scoro invoice and new data,
        if changes are present, collect them into string report"""

        changed_values = {}
        # Check non-sensitive fields
        date_due = new_data.get('deadline')
        if scoro_invoice.date_due != date_due:
            # Just write to the invoice
            scoro_invoice.invoice_id.write({'date_due': date_due})
            changed_values['date_due'] = date_due

        status = new_data.get('status')
        if scoro_invoice.paid_state != status:
            changed_values['status'] = status

        # Check for sensitive fields
        change_report = str()
        date = new_data.get('date')
        if scoro_invoice.date_invoice != date:
            changed_values['date_invoice'] = date
            change_report += '{} -> {} // Sąskaitos data\n'.format(scoro_invoice.date_invoice, date)

        sum_wo_vat = float(new_data.get('sum', 0))
        if tools.float_compare(scoro_invoice.sum_wo_vat, sum_wo_vat, precision_digits=2):
            changed_values['sum_wo_vat'] = sum_wo_vat
            change_report += '{} -> {} // Suma\n'.format(scoro_invoice.sum_wo_vat, sum_wo_vat)

        vat_rate = float(new_data.get('vat', 0))
        if tools.float_compare(scoro_invoice.vat_rate, vat_rate, precision_digits=2):
            changed_values['vat_rate'] = vat_rate
            change_report += '{} -> {} // PVM Procentas\n'.format(scoro_invoice.vat_rate, vat_rate)

        vat_sum = float(new_data.get('vat_sum', 0))
        if tools.float_compare(scoro_invoice.vat_sum, vat_sum, precision_digits=2):
            changed_values['vat_sum'] = vat_sum
            change_report += '{} -> {} // PVM Suma\n'.format(scoro_invoice.vat_sum, vat_sum)

        paid_sum = float(new_data.get('paid_sum', 0))
        if tools.float_compare(scoro_invoice.paid_sum, paid_sum, precision_digits=2):
            changed_values['paid_sum'] = paid_sum
            change_report += '{} -> {} // Apmokėjimo Suma\n'.format(scoro_invoice.paid_sum, paid_sum)

        ext_company_id = new_data.get('company_id', 0)
        if scoro_invoice.company_id != ext_company_id:
            partner = self.env['res.partner'].search([('scoro_external_id', '=', ext_company_id)])
            if not partner:
                partner = self.env['scoro.data.fetcher'].fetch_create_partner_single(ext_company_id)
            changed_values['partner_id'] = partner.id
            change_report += '{} -> {} // Partneris\n'.format(scoro_invoice.partner_id.name, partner.name)

        external_number = new_data.get('no', str())
        if external_number not in scoro_invoice.internal_number:
            changed_values['external_number'] = external_number
            change_report += '{} -> {} // Išorinis numeris\n'.format(scoro_invoice.external_number, external_number)

        # If there's any changed values, write them to the scoro invoice
        if changed_values:
            scoro_invoice.write(changed_values)

        lines = scoro_invoice.scoro_invoice_line_ids
        change_report_lines = str()
        for line in new_data.get('lines'):
            external_id = line.get('id')
            system_line = lines.filtered(lambda x: x.external_id == external_id)
            if system_line:
                line_changes = {}
                quantity = float(line.get('amount', 0))
                if tools.float_compare(system_line.quantity, quantity, precision_digits=2) != 0:
                    line_changes['quantity'] = quantity
                    change_report_lines += 'Eilutė {} // {} -> {} // Kiekis\n'.format(
                        system_line.line_name, system_line.quantity, line.get('amount', 0))

                discount = float(line.get('discount', 0))
                if tools.float_compare(system_line.discount, discount, precision_digits=2) != 0:
                    line_changes['discount'] = discount
                    change_report_lines += 'Eilutė {} // {} -> {} // Nuolaida\n'.format(
                        system_line.line_name, system_line.discount, line.get('discount', 0))

                price_unit = float(line.get('price', 0))
                if tools.float_compare(system_line.price_unit, price_unit, precision_digits=2) != 0:
                    line_changes['price_unit'] = price_unit
                    change_report_lines += 'Eilutė {} // {} -> {} // Vieneto kaina\n'.format(
                        system_line.line_name, system_line.price_unit, line.get('price', 0))

                sum_wo_vat = float(line.get('sum', 0))
                if tools.float_compare(system_line.sum_wo_vat, sum_wo_vat, precision_digits=2) != 0:
                    line_changes['sum_wo_vat'] = sum_wo_vat
                    change_report_lines += 'Eilutė {} // {} -> {} // Suma be PVM\n'.format(
                        system_line.line_name, system_line.sum_wo_vat, line.get('price', 0))

                line_name = line.get('comment')
                if system_line.line_name != line_name:
                    line_changes['line_name'] = line_name
                    change_report_lines += 'Eilutė {} // {} -> {} // Pavadinimas\n'.format(
                        system_line.line_name, system_line.line_name, line_name)

                if change_report_lines:
                    system_line.write(line_changes)
                    change_report_lines = '\nEilučių pokyčiai: \n' + change_report_lines

        if change_report:
            change_report = '\nSąskaitos {} pasikeitimai: \n'.format(scoro_invoice.internal_number) + change_report
            if change_report_lines:
                change_report += change_report_lines
            change_report += '\n' + '-' * 20
        return change_report

    @api.model
    def inform_accountant(self, report, subject):

        """Send mail to main accountant of the company"""
        # Add information header
        report = _(
            'Sąskaitos bandomos koreguoti automatiškai. '
            'Nepavykę bandymai pažymėti prie specifinės SF. \n\n\n'
        ) + report

        findir_email = self.sudo().env.user.company_id.findir.partner_id.email
        database = self._cr.dbname
        subject = '{} // [{}]'.format(subject, database)
        self.env['script'].send_email(emails_to=[findir_email],
                                      subject=subject,
                                      body=report)

    @api.model
    def create_scoro_invoice(self, line):

        """Create scoro_invoice based on data passed from scoro system"""

        def list_to_char(passed_list):
            string_repr = str()
            if passed_list:
                for rec in passed_list:
                    string_repr += str(rec) + ','
            return string_repr
        scoro_invoice_line_ids = []

        vat_rate = line.get('vat')
        invoice_based_tax = False if vat_rate is None else True
        external_number = line.get('no')
        external_id = line.get('id')
        if not external_id or not external_number:
            return self.env['scoro.invoice']

        vals = {
            'external_number': external_number,
            'external_invoice_ref': line.get('reference_no'),
            'external_id': external_id,
            'payment_type': line.get('payment_type', 'cash'),
            'fine_percentage': line.get('fine', ''),
            'credited_invoices_ids_char': list_to_char(line.get('credited_invoices', [])),
            'company_name': line.get('company_name', ''),
            'person_name': line.get('person_name', ''),
            'paid_sum': line.get('paid_sum', 0),
            'receivable_sum': line.get('receivable_sum', 0),
            'currency_rate': line.get('currency_rate', 1),
            'real_estate_id': line.get('real_estate_id', 0),
            'discount': line.get('discount', 0),
            'sum_wo_vat': line.get('sum', 0),
            'vat_sum': line.get('vat_sum', 0),
            'vat_code_id': line.get('vat_code_id', 0),
            'vat_rate': line.get('vat', 0),
            'company_id': line.get('company_id', 0),
            'person_id': line.get('person_id', 0),
            'company_address_id': line.get('company_address_id', 0),
            'interested_party_id': line.get('interested_party_id', 0),
            'interested_party_address_id': line.get('interested_party_address_id', 0),
            'project_id': line.get('project_id', 0),
            'currency_code': line.get('currency_code', 'EUR'),
            'date_invoice': line.get('date'),
            'date_due': line.get('deadline'),
            'paid_state': line.get('status', 'unpaid'),
            'description': line.get('description'),
            'is_deleted_scoro': line.get('is_deleted'),
            'deleted_date': line.get('deleted_date'),
            'system_move_state': 'waiting' if line.get('paid_sum', 0) else 'no_action',
            'scoro_invoice_line_ids': scoro_invoice_line_ids,
            'invoice_based_tax': invoice_based_tax
        }

        for inv_line in line.get('lines'):
            line_vals = {
                'external_id': inv_line.get('id'),
                'product_name': inv_line.get('product_name'),
                'product_code': inv_line.get('product_code'),
                'external_product_id': inv_line.get('product_id'),
                'margin_supplier_name': inv_line.get('supplier_name'),
                'margin_cost': inv_line.get('cost'),
                'margin_supplier_id': inv_line.get('supplier_id'),
                'finance_account_name': inv_line.get('finance_account_name', ''),
                'finance_account_id': inv_line.get('finance_account_id', 0),
                'project_name': inv_line.get('project_name', ''),
                'project_id': inv_line.get('project_id', 0),
                'line_name': inv_line.get('comment', ''),
                'add_line_name': inv_line.get('comment2', ''),
                'price_unit': inv_line.get('price', 0),
                'quantity': inv_line.get('amount', 0),
                'add_quantity': inv_line.get('amount2', 0),
                'discount': inv_line.get('discount', 0),
                'sum_wo_vat': inv_line.get('sum', 0),
                'unit_name': inv_line.get('unit', 0),
                'is_internal': inv_line.get('is_internal', 0),
                'vat_rate': inv_line.get('vat'),
                'vat_code': inv_line.get('vat_code'),
                'vat_code_id': inv_line.get('vat_code_id'),
            }
            scoro_invoice_line_ids.append((0, 0, line_vals))
        scoro_invoice_id = self.env['scoro.invoice'].create(vals)
        return scoro_invoice_id

    @api.multi
    def cron_fetch_daily_data(self):

        """Daily cron job that fetches data (invoices so far) and creates scoro.invoices / account.invoices"""

        config_obj = self.sudo().env['ir.config_parameter']
        sync_date = self.env.user.company_id.scoro_db_sync
        threshold_accounting = config_obj.get_param('scoro_threshold_accounting')

        date_to_use = sync_date if sync_date else threshold_accounting

        # fetch invoices
        endpoint = self.get_api('invoice_list')

        # todo: make filter dict more sophisticated if it's needed in the future
        # todo: IMPORTANT - BY DEFAULT SCORO GIVES 100 RECS IN THE RESPONSE
        filter_dict = {'modified_date': {'from_date': date_to_use}}
        data = self.get_request_template(filter_dict=filter_dict)
        resp = requests.post(endpoint, json=data)
        change_report = str()
        try:
            ids_list = []
            fetched_data = json.loads(resp.text)
            response = validate_response(fetched_data)
            if response:
                self.send_bug(response)
                return
            data_set = fetched_data.get('data')
            if not data_set:
                return
            for line in data_set:
                ids_list.append(line.get('id'))

            req_template = self.get_request_template()
            scoro_invoice_ids = self.env['scoro.invoice']
            for line in ids_list:
                endpoint = self.get_api('invoice_id', object_id=line)
                full_invoice_data = requests.post(endpoint, json=req_template)
                fetched_data = json.loads(full_invoice_data.text)
                response = validate_response(fetched_data)
                if response:
                    self.send_bug(response)
                    return
                invoice_data = fetched_data.get('data')
                if not invoice_data:
                    continue
                skip, report = self.check_scoro_invoice(invoice_data)
                change_report += report
                if skip:
                    continue
                scoro_invoice_id = self.create_scoro_invoice(invoice_data)
                scoro_invoice_ids += scoro_invoice_id
            self.env.user.company_id.write({'scoro_db_sync': datetime.utcnow().strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)})
            scoro_invoice_ids.create_invoices_prep()
        except Exception as exc:
            if change_report:
                self.inform_accountant(change_report, 'Scoro sąskaitų koregavimai')
            exception = 'Scoro API connection exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return
        if change_report:
            self.inform_accountant(change_report, 'Scoro sąskaitų koregavimai')

        # todo: expand integration in the future

    @api.model
    def cron_fetch_partner_list(self):

        """Weekly cron that fetches and creates list of partners
        from scoro system and creates them in res.partner table"""

        endpoint = self.get_api('partner_list')
        data = self.get_request_template()
        resp = requests.post(endpoint, json=data)
        try:
            fetched_data = json.loads(resp.text)
            response = validate_response(fetched_data)
            if response:
                self.send_bug(response)
                return
            data_set = fetched_data.get('data')
            if not data_set:
                return
            for line in data_set:
                self.create_res_partner(line)

        except Exception as exc:
            exception = 'Scoro partner API connection exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return

    @api.model
    def cron_data_recreate(self):

        """Daily cron to re-create failed records"""

        scoro_invoice_ids = self.env['scoro.invoice'].search([('state', 'in', ['failed', 'imported']),
                                                              ('invoice_id', '=', False)])
        scoro_invoice_ids.create_invoices_prep()

    @api.model
    def fetch_create_partner_single(self, ext_partner_id):

        """Fetches and creates single partner based on external scoro id"""

        endpoint = self.get_api('partner_id', object_id=ext_partner_id)
        data = self.get_request_template()
        resp = requests.post(endpoint, json=data)
        try:
            fetched_data = json.loads(resp.text)
            response = validate_response(fetched_data)
            if response:
                self.send_bug(response)
                return
            data_set = fetched_data.get('data')
            if not data_set:
                return
            return self.create_res_partner(data_set)

        except Exception as exc:
            exception = 'Scoro partner API connection exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return

    @api.model
    def fetch_create_product_single(self, ext_product_id):

        """Fetches and creates single product based on external scoro id"""

        endpoint = self.get_api('product_id', object_id=ext_product_id)
        data = self.get_request_template()
        resp = requests.post(endpoint, json=data)
        try:
            fetched_data = json.loads(resp.text)
            response = validate_response(fetched_data)
            if response:
                self.send_bug(response)
                return
            data_set = fetched_data.get('data')
            if not data_set:
                return
            self.create_product_product(data_set)

        except Exception as exc:
            exception = 'Scoro partner API connection exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return

    @api.model
    def cron_fetch_tax_list(self):
        endpoint = self.get_api('vat_code_list')
        data = self.get_request_template()
        resp = requests.post(endpoint, json=data)
        try:
            tax_list = self.env['scoro.tax']
            fetched_data = json.loads(resp.text)
            response = validate_response(fetched_data)
            if response:
                self.send_bug(response)
                return
            data_set = fetched_data.get('data')
            if not data_set:
                return
            for line in data_set:
                tax_list |= self.create_scoro_tax(line)
            tax_list.recompute_taxes()
        except Exception as exc:
            exception = 'Scoro API connection exception - {}'.format(exc.args[0])
            self.send_bug(exception)
            return

    def send_bug(self, body):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })


ScoroDataFetcher()
