# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, tools
from .. model import robo_api_tools as at
from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class ApiController(http.Controller):

    # Utility methods -------------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @staticmethod
    def check_credentials(api_request, accounting=False):
        """
        Check whether secret key in post matches secret key of the company
        Return response text and the code or empty dictionary
        :param api_request: Http request object
        :param accounting: Indication if accounting API key should be checked
        :return: response info (dict)
        """
        post = api_request.jsonrequest
        api_key_header = api_request.httprequest.headers.environ.get('HTTP_X_API_KEY')
        api_key_body = post.get('secret')
        secret = api_key_header or api_key_body
        env = api_request.env
        company = env.user.sudo().company_id
        api_secret = company.api_secret if not accounting else company.api_secret_gl
        if not secret:
            return {'error': 'Access denied', 'code': at.API_INVALID_CRED}
        if not api_secret or secret != api_secret:
            return {'error': 'Access denied. Incorrect credentials.', 'code': at.API_INVALID_CRED}
        return {}

    @staticmethod
    def check_call_limit(api_request):
        """
        Check API call limits
        :return: response info (dict)
        """

        env = api_request.env
        company = env.user.sudo().company_id
        if company.api_woocommerce_integration or company.api_prestashop_integration:
            return {}

        IrConfig = env['ir.config_parameter'].sudo()
        RoboAPIJob = env['robo.api.job'].sudo()
        limit_per_hour = IrConfig.get_param('robo_api_call_limit_per_hour')
        limit_per_min = IrConfig.get_param('robo_api_call_limit_per_minute')

        if not isinstance(limit_per_hour, int):
            try:
                limit_per_hour = int(limit_per_hour)
            except (ValueError, TypeError):
                limit_per_hour = 500

        if not isinstance(limit_per_min, int):
            try:
                limit_per_min = int(limit_per_min)
            except (ValueError, TypeError):
                limit_per_min = 10

        date_from_dt = datetime.utcnow() + timedelta(minutes=-1)

        call_num = RoboAPIJob.search_count([
            ('registration_date', '>=', date_from_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),
            ('registration_date', '<=', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))])

        if limit_per_min and call_num >= limit_per_min:
            return {'error': 'Limit of maximum API calls per minute exceeded', 'code': at.API_TOO_MANY_REQUESTS}

        date_from_dt = datetime.utcnow() + timedelta(hours=-1)

        call_num = RoboAPIJob.search_count([
            ('registration_date', '>=', date_from_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),
            ('registration_date', '<=', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))])

        if limit_per_hour and call_num >= limit_per_hour:
            return {'error': 'Limit of maximum API calls per hour exceeded', 'code': at.API_TOO_MANY_REQUESTS}
        return {}

    @staticmethod
    def response(api_request, code, error=str(), data=None):
        """
        Format API response
        :param api_request: Http request object
        :param code: response code
        :param error: error message
        :param data: extra data
        :return: formatted response
        """
        data = [] if data is None else data
        if code != at.API_SUCCESS:
            api_request.env.cr.rollback()
        return {
            'data': data,
            'error': error,
            'status_code': code,
        }

    @staticmethod
    def format_api_exception(api_request, exc):
        """
        Format API exception message
        :param api_request: Http request object
        :param exc: exception obj
        :return: result of ApiController.response (dict)
        """
        post = api_request.jsonrequest
        post.pop('secret', False)
        post.pop('file_data', False)  # Large value encoded in base64
        _logger.info('ROBO API EXCEPTION: %s' % str(exc.args))
        _logger.info('ROBO API EXCEPTION REQUEST: %s' % post)
        if 'debug' in post and post['debug'] == 'robotukai':
            response = {
                'error': 'Unexpected error. Exception: %s. Request: %s' % (str(exc.args), post),
                'code': at.API_INTERNAL_SERVER_ERROR
            }
            return ApiController.response(api_request, **response)
        else:
            response = {
                'error': 'Unexpected error',
                'code': at.API_INTERNAL_SERVER_ERROR
            }
            return ApiController.response(api_request, **response)

    # Product API Routes ----------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @http.route(['/api/create_product'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_product(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'name': 'New product name',
                'type': 'product' or 'service',
                'default_code': 'PROD0001',
                'vat_code': PVM1,PVM2, or PVM3,
                'categ_id': ID,
                'price': 2.55,
                'sync_price': 0 or 1,
                'price_with_vat':3.09,
                'barcode': '123456789012',
            }
        """
        try:
            # Get environment
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='create_product', json_data=post)
            return self.response(request, **api_res)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/update_product'], type='json', auth='public', methods=['POST'], csrf=False)
    def update_product(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'product_id': 2,
                'name': 'Product name',
                'default_code': 'PROD0001',
                'type': 'product' or 'service',
                'vat_code': PVM1,PVM2, or PVM3,
                'categ_id': 4,
                'price': 2.55,
                'barcode': '123456789012',
            }
        """
        try:
            # Get environment
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='update_product', json_data=post)
            return self.response(request, **api_res)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/new_products'], type='json', auth='public', methods=['POST'], csrf=False)
    def new_products(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'date_from': '2018-01-01 00:00:00',
                'date_to': '2018-01-31 00:00:00'
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='new_products', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/products'], type='json', auth='public', methods=['POST'], csrf=False)
    def products(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'warehouse': 'WH',
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='products', json_data=post)
            return self.response(request, **api_res)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/write_off_products'], type='json', auth='public', methods=['POST'], csrf=False)
    def write_off_products(self, **post):
        """
        Sample request:
            post = {
            'secret': 'API_SECRET',
            'name': 'XXX',
            'warehouse_code': 'WH',
            'committee': 'Committee',
            'accounting_date': '2022-06-15',
            'reason_line': 'Reason',
            'account_code': 'XXXX',
            'analytic_code': 'XXXXX',
            'products':
            [
                {
                    'code': 'XXXXX',
                    'consumed_qty': 1.00,
                },
            ],
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='write_off_products', json_data=post)
            return self.response(request, **api_res)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    # Product category API Routes -------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @http.route(['/api/product_categories'], type='json', auth='public', methods=['POST'], csrf=False)
    def product_categories(self, **post):
        """
        Sample request:
        post = {
                'secret': 'API_SECRET',
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='product_categories', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/create_product_category'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_product_category(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'name': 'XXX',
                'type': 'products'
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='create_product_category', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/update_product_category'], type='json', auth='public', methods=['POST'], csrf=False)
    def update_product_category(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'categ_id': 5,
                'name': 'XXX',
                'type': 'products'
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='update_product_category', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    # Invoice API Routes ----------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @http.route(['/api/create_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_invoice(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'journal': 'XXX',
                'date_invoice': '2017-08-28',
                'due_date': '2017-09-28',
                'number': 'EST00001',
                'proforma': True,
                'currency': 'EUR',
                'subtotal': 100.0,
                'tax': 21.0,
                'total': 121.0,
                'warehouse_cost': 120.0,
                'partner': {
                    'name': 'Client Name',
                    'is_company': True,
                    'company_code': '123456789',
                    'vat_code': 'LT123456715',
                    'street': 'Gatve 1',
                    'city': 'Vilnius',
                    'zip': 'LT-12345',
                    'country': 'LT',
                    'phone': '+370612345678',
                    'email': 'email@email.com',
                    'tags': ['Printing services', 'Computer trading'],
                    'partner_category': 'IT Related services',
                    'bank_account': {
                        'bank_name': 'Swedbank',
                        'bank_code': '73000',
                        'bic': 'HABALT22',
                        'acc_number': 'LT601010012345678901'
                    },
                },
                'invoice_lines':
                [
                    {
                        'product': 'Paslaugos',
                        'description': 'Paslaugos pagal sutartį X',
                        'price': 100.0,
                        'qty': 1.0,
                        'vat': 21.0,
                        'vat_code': 'PVM1',
                        'price_with_vat': 121.0
                    },
                ],
                'payments': [
                    {
                        'payer': 'Vardenis Pavardenis',
                        'currency': 'EUR',
                        'amount': 100.0,
                        'date': '2018-03-29',
                        'ref': 'f64c2909-e33c-48e2-8aa7-cd0bdc697ee7',
                        'name': 'Mokėjimas X',
                        'journal_code': 'STRIPE1',
                        'journal_name': 'Stripe projektas X'
                    },
                ],
                'location': 'WH01',
                'use_credit': True,
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='create_invoice', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/update_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def update_invoice(self, **post):
        """
        Sample request:
        post = {
                'secret': '',
                'date_invoice': '2017-08-28',
                'due_date': '2017-09-28',
                'number': 'EST00001',
                'proforma': True,
                'currency': 'EUR',
                'warehouse_cost': 120.0,
                'partner': {
                    'name': 'Client Name',
                    'is_company': True,
                    'company_code': '123456789',
                    'vat_code': 'LT123456715',
                    'street': 'Gatve 1',
                    'city': 'Vilnius',
                    'zip': 'LT-12345',
                    'country': 'LT',
                    'phone': '+370612345678',
                    'email': 'email@email.com',
                    'tags': ['Printing services', 'Computer trading'],
                    'partner_category': 'IT Related services',
                    'bank_account': {
                        'bank_name': 'Swedbank',
                        'bank_code': '73000',
                        'bic': 'HABALT22',
                        'acc_number': 'LT601010012345678901'
                    },
                },
                'invoice_lines':
                [
                    {
                        'product': 'Paslaugos',
                        'price': 100.0,
                        'qty': 1.0,
                        'vat': 21.0,
                        'vat_code': 'PVM1',
                        'price_with_vat': 121.0
                    },
                ],
                'add_payments': [
                    {
                        'payer': 'Vardenis Pavardenis',
                        'currency': 'EUR',
                        'amount': 100.0,
                        'date': '2018-03-29',
                        'ref': '3404-20161124213050',
                        'name': 'f64c2909-e33c-48e2-8aa7-cd0bdc697ee7',
                    },
                ]
                'use_credit': True,
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='update_invoice', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/cancel_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def cancel_invoice(self, **post):
        """
        Endpoint used to cancel the account.invoice record
        Sample request:
        post = {
                'reference': 'ROBO123',
                'number': 'ROBO123',
                'partner_reference': '123456789',
                'secret': '123466789',
            }
            number  <- Signifies the invoice number that is generated by ROBO (Used for client invoices)
            reference  <- Signifies the invoice number that is external to ROBO (Used for supplier invoices)
            partner_reference <- mandatory if no number is provided so we can prevent reference ambiguity,
                can be either partner code or partner name
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='cancel_invoice', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/unlink_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def unlink_invoice(self, **post):
        """
        Sample request:
        post = {
                'reference': 'ROBO123',
                'move_name': 'ROBO123',
                'partner_code': '123456789',
                'delete_payment': True,
                'secret': '123466789',
            }
        partner_code is mandatory if no move_name is provided so we can prevent reference ambiguity.
        delete_payment indicates whether payment that is reconciled with the invoice should be deleted as well
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='unlink_invoice', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/get_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def get_invoice(self, **post):
        """
        Not Threaded//
        Sample request, at least one of the identifying fields must be specified
        post = {
                'secret': 789,
                'invoice_number': 'TEST-14789',  <-- Number in the system given by ROBO sequence
                'invoice_reference': 'TEST-14789',  <-- Number in the system that the supplier provides
                'partner_code': '378965478',  <-- Is required when reference is provided
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(
                method_name='get_invoice', json_data=post, force_non_threaded=True)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/get_invoice_list'], type='json', auth='public', methods=['POST'], csrf=False)
    def get_invoice_list(self, **post):
        """
        Sample request:
        post = {
                'secret': 789,
                'invoice_date_from': '2018-01-01',
                'invoice_date_to': '2018-12-31',
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(
                method_name='get_invoice_list', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/add_invoice_document'], type='json', auth='public', methods=['POST'], csrf=False)
    def add_invoice_document(self, **post):
        """
        Specific execution - invoice document is created instantly and if the creation is successful, job is set to
        attach it to invoice or is attached instantly according to the execution type
        Sample request:
        post = {
                'secret': '',
                'invoice_number': 'TEST-14789',
                'file_name': 'TEST-14789-SF',
                'file_data': '' <-- BASE64 encoded file data
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='add_invoice_document', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/create_partner_payments'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_partner_payments(self, **post):
        """
        Sample request:
        post = {
                'secret': 789,
                'name': 'Client Name',
                'company_code': '123456789',
                'vat_code': 'LT123456715',
                'payments': [
                    {
                        'payer': 'Vardenis Pavardenis',
                        'currency': 'EUR',
                        'amount': 100.0,
                        'date': '2018-03-29',
                        'ref': 'f64c2909-e33c-48e2-8aa7-cd0bdc697ee7',
                        'name': 'Mokėjimas X',
                        'journal_code': 'STRIPE1',
                        'journal_name': 'Stripe projektas X'
                    },
                ],
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='create_partner_payments', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/create_accounting_entries'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_accounting_entries(self, **post):
        """
        Sample request:
        post = {
                'secret': XXX,
                'entries': [
                    {
                        'entry_name': 'Entry X',
                        'partner_name': 'Partner X',
                        'date': '2021-03-29',
                        'journal_code': 'KITA',
                        'debit': 0.0,
                        'credit': 50.0,
                        'account_code': '2410'
                    },
                    {
                        'entry_name': 'Entry Y',
                        'partner_name': 'Partner Y',
                        'date': '2021-03-29',
                        'journal_code': 'KITA',
                        'debit': 50.0,
                        'credit': 0.0,
                        'account_code': '4430'
                    }
                ]
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request, accounting=True)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='create_accounting_entries', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/get_accounting_entries'], type='json', auth='public', methods=['POST'], csrf=False)
    def get_accounting_entries(self, **post):
        """
        Sample request:
        post = {
                'secret': XXX,
                'date_from': '2018-01-01',
                'date_to': '2018-12-31',
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            # Check credentials
            res = self.check_credentials(request, accounting=True)
            if res:
                return self.response(request, **res)

            # Check limit of API calls
            res = self.check_call_limit(request)
            if res:
                return self.response(request, **res)

            # Call API Job, let it decide whether the mode is threaded and return the response
            api_res = env['robo.api.job'].execute_api_action(method_name='get_accounting_entries', json_data=post)
            return self.response(request, **api_res)

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    # Threaded Job API Routes -----------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------
    # Methods themselves are not threaded since they are used to fetch thread results
    # thus record limiting is enabled

    @http.route(['/api/get_api_job'], type='json', auth='public', methods=['POST'], csrf=False)
    def get_api_job(self, **post):
        """
        Not Threaded //
        Return API job information based on the provided ID.
        post = {
                'secret': 6789, <-- API Secret key provided by ROBO
                'api_job_id': 1234,  <-- ID of the api_job
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            if not env.user.company_id.enable_threaded_api:
                return self.response(request, at.API_NOT_FOUND, error='Endpoint not found.')

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            api_job_id = post.get('api_job_id')
            if not api_job_id:
                return self.response(request, at.API_INCORRECT_DATA, error='API Job ID is not specified!')

            # Sanitize passed ID element
            if not isinstance(api_job_id, int):
                if not isinstance(api_job_id, basestring) or not api_job_id.isdigit():
                    return self.response(
                        request, at.API_INCORRECT_DATA,
                        error='API Job ID is of incorrect format. Integer must be passed.')
                else:
                    api_job_id = int(api_job_id)

            # Search for the API job. Do not use browse, since it always finds a record
            # No matter what the ID is.
            api_job = env['robo.api.job'].search([('id', '=', api_job_id)])
            if not api_job:
                return self.response(request, at.API_NOT_FOUND,
                                     error='API Job {} could not be found!'.format(api_job_id))

            data = api_job.api_job_repr()
            return self.response(request, at.API_SUCCESS, data=data)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/get_api_job_list'], type='json', auth='public', methods=['POST'], csrf=False)
    def get_api_job_list(self, **post):
        """
        Not Threaded //
        Result is always limited to 100 records, since the method is not threaded.
        Use possible state or date filters to get the data.
        Return API job information based date and state parameters.
        post = {
                'secret': 6789, <-- API Secret key provided by ROBO
                'date_from': '2020-01-01 00:00:00',  <-- Job registration date from (non-required)
                'date_to': '2020-02-01 00:00:00',  <-- Job registration date to (non-required)
                'state': 'failed' <-- Job state (non-required)
            }
        """
        try:
            post = request.jsonrequest
            env = api.Environment(request.cr, SUPERUSER_ID, dict(request.context, **{'lang': 'lt_LT'}))

            if not env.user.company_id.enable_threaded_api:
                return self.response(request, at.API_NOT_FOUND, error='Endpoint not found.')

            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            api_job_domain = []
            expected_format = 'Expected Format - YYYY-MM-DD HH:MM:SS'

            date_from = post.get('date_from')
            if date_from:
                try:
                    datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    api_job_domain.append(('registration_date', '>=', date_from))
                except (ValueError, TypeError):
                    return self.response(
                        request, at.API_INCORRECT_DATA,
                        error='Date from is of incorrect format. Expected format: {}'.format(expected_format))
            date_to = post.get('date_to')
            if date_to:
                try:
                    datetime.strptime(date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    api_job_domain.append(('registration_date', '<=', date_to))
                except (ValueError, TypeError):
                    return self.response(
                        request, at.API_INCORRECT_DATA,
                        error='Date to is of incorrect format. Expected format: {}'.format(expected_format))

            state = post.get('state')
            if state:
                if not isinstance(state, basestring):
                    return self.response(request, at.API_INCORRECT_DATA,
                                         error='Incorrect format. "state" should be a string')
                if state not in at.ROBO_API_JOB_STATES:
                    return self.response(
                        request, at.API_INCORRECT_DATA,
                        error='Incorrect state. Possible states: {}'.format(at.ROBO_API_JOB_STATES))
                api_job_domain.append(('state', '=', state))

            # Search for the API jobs, always limit to 100 records
            api_jobs = env['robo.api.job'].search(api_job_domain, limit=100)
            if not api_jobs:
                return self.response(request, at.API_NOT_FOUND, error='No jobs for passed criteria were found!')

            final_data = []
            for api_job in api_jobs:
                # Loop through jobs and gather their repr
                data = api_job.api_job_repr()
                final_data.append(data)
            return self.response(request, at.API_SUCCESS, data=final_data)
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)
