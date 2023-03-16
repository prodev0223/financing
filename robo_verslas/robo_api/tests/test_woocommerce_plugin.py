# -*- coding: utf-8 -*-
from odoo import tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.tests import common, tagged
from ..model import robo_api_tools as at


@tagged('post_install', 'robo')
class TestWoocommercePlugin(common.SingleTransactionCase):
    """
    Tests the query structure set up in WooCommerce plugin (corresponding to the fields and methods used)
    """
    @classmethod
    def setUpClass(cls):
        super(TestWoocommercePlugin, cls).setUpClass()
        TaxPosition = cls.env['robo.api.force.tax.position']
        AccountTax = cls.env['account.tax']
        ResCountry = cls.env['res.country'].sudo()

        cls.api_secret = 'WooCommerceRoboAPIUnitTest'
        cls.RoboApiJob = cls.env['robo.api.job']
        cls.RoboApiBase = cls.env['robo.api.base']
        today = datetime.today()
        cls.invoice_date = today.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        # Set up company settings
        cls.env.user.sudo().company_id.write({
            'api_force_tax_selection': 'selective'
        })

        cls.env.user.sudo().company_id.write({
            'api_secret': cls.api_secret,
            'prevent_empty_product_code': True,
            'prevent_duplicate_product_code': True,
            'api_woocommerce_integration': True,
            'api_force_tax_condition': 'force_if_none',
        })
        # Set up tax positions
        TaxPosition.search([]).unlink()
        oss_moss_tax = AccountTax.search([('price_include', '=', True), ('code', '=', 'Ne PVM'),
                                          ('type_tax_use', '=', 'sale')], limit=1)
        oss_moss_tax_position_values = {
            'name': 'OSS/MOSS',
            'date_from': '2021-07-01',
            'partner_type': 'physical',
            'partner_vat_payer_type': 'not_vat_payer',
            'product_type': 'all',
            'force_tax_type': 'price_include',
            'force_tax_id': oss_moss_tax.id,
            'country_group_id': cls.env.ref('base.europe', False).id
        }
        TaxPosition.create(oss_moss_tax_position_values)

        lithuania_tax = AccountTax.search([('price_include', '=', True), ('code', '=', 'PVM1'),
                                          ('type_tax_use', '=', 'sale')], limit=1)
        lithuania_tax_position_values = {
            'name': 'Lietuva - PVM1',
            'date_from': '2021-07-01',
            'partner_type': 'all',
            'partner_vat_payer_type': 'all',
            'product_type': 'all',
            'force_tax_type': 'price_include',
            'force_tax_id': lithuania_tax.id,
            'country_id': ResCountry.search([('code', '=', 'LT')], limit=1).id
        }
        TaxPosition.create(lithuania_tax_position_values)

        europe_country_group_id = cls.env.ref('base.europe', False).id
        eu_vat_payer_tax = AccountTax.search([('price_include', '=', True), ('code', '=', 'PVM13'),
                                              ('type_tax_use', '=', 'sale')], limit=1)
        eu_vat_payer_tax_position_values = {
            'name': 'ES PVM mokėtojai',
            'date_from': '2021-07-01',
            'partner_type': 'all',
            'partner_vat_payer_type': 'vat_payer',
            'product_type': 'all',
            'force_tax_type': 'price_include',
            'force_tax_id': eu_vat_payer_tax.id,
            'country_group_id': europe_country_group_id
        }
        TaxPosition.create(eu_vat_payer_tax_position_values)

        eu_juridical_non_vat_payer_tax = AccountTax.search([('price_include', '=', True), ('code', '=', 'PVM1'),
                                                            ('type_tax_use', '=', 'sale')], limit=1)
        eu_juridical_non_vat_payer_tax_position_values = {
            'name': 'ES juridiniai (nemokantys PVM)',
            'date_from': '2021-07-01',
            'partner_type': 'juridical',
            'partner_vat_payer_type': 'not_vat_payer',
            'product_type': 'all',
            'force_tax_type': 'price_include',
            'force_tax_id': eu_juridical_non_vat_payer_tax.id,
            'country_group_id': europe_country_group_id
        }
        TaxPosition.create(eu_juridical_non_vat_payer_tax_position_values)

    def test_01__create_product_category(self):
        post = {'secret': self.api_secret, 'execute_immediately': True, 'type': 'products',
                'name': 'RoboAPI TestProductCategory'}

        base_method_name = at.API_METHOD_MAPPING.get('create_product_category')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the category should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(type(response.get('data').get('id')), int)

        category_id = response.get('data').get('id')
        category = self.env['product.category'].browse(category_id).exists()
        self.assertTrue(len(category))
        # Try to create again
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the category should not be created
        self.assertEqual(str(response.get('error')), 'Category with this name already exists.')
        self.assertEqual(response.get('code'), 401)
        self.assertEqual(response.get('system_error'), str())
        self.assertFalse(len(response.get('data')))

    def test_02__create_product(self):
        category_id = self.env.ref('l10n_lt.product_category_30', False).id
        post = {'secret': self.api_secret, 'name': 'Test Product 1', 'default_code': 'TP1', 'type': 'service',
                'vat_code': 'PVM1', 'categ_id': category_id, 'price': 1.0}

        base_method_name = at.API_METHOD_MAPPING.get('create_product')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the product should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertFalse(len(response.get('data')))

    def test_03__create_order_lithuanian_partner(self):
        # Base test record names
        invoice_number, product_code, product_name, partner_name = \
            'RoboAPITestInvoiceNumber1', 'TP1', 'Test Product 1', 'Robo API Test Partner 1'

        post = {'due_date': self.invoice_date,
                'invoice_lines': [{'product': product_name, 'product_id': 1537, 'price': 44.6198345, 'qty': 2,
                                   'vat_code': 'PVM1', 'product_code': product_code, 'vat': 18.74,
                                   'description': product_name + ' Description'}], 'journal': 'RoboAPI',
                'number': invoice_number, 'date_invoice': self.invoice_date, 'currency': 'EUR',
                'secret': self.api_secret, 'payments': [{'date': self.invoice_date, 'amount': 107.98,
                                                         'payer': partner_name}],
                'partner': {'city': 'Test City', 'company_code': '', 'name': partner_name,
                            'zip': '123456', 'country': 'LT', 'phone': '123456789', 'street': 'Test Street',
                            'vat_code': '', 'email': 'testemail@gmail.com', 'is_company': False},
                'force_type': 'out_invoice'}

        base_method_name = at.API_METHOD_MAPPING.get('create_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the invoice should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(len(response.get('data')), 0)

        # Check partner to be physical
        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
        self.assertEqual(partner.country_id.code, 'LT')
        self.assertFalse(partner.is_company)

        # Check invoice
        invoice = self.env['account.invoice'].search([('number', '=', invoice_number)], limit=1)
        # Check state and amounts
        self.assertEqual(invoice.state, 'paid')
        self.assertTrue(invoice.price_include)
        self.assertFalse(invoice.has_outstanding)
        self.assertEqual(invoice.amount_total, 107.98)
        self.assertEqual(round(invoice.amount_tax, 2), 18.74)
        self.assertEqual(invoice.amount_untaxed, 89.24)

        # Other base fields check for test coverage - not present in the remaining invoice creation tests
        self.assertEqual(invoice.type, 'out_invoice')
        self.assertEqual(invoice.partner_id.id, partner.id)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertTrue(invoice.imported_api)
        self.assertEqual(invoice.date_invoice, self.invoice_date)
        self.assertEqual(invoice.currency_id.name, 'EUR')

        # Check invoice line
        invoice_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id.default_code == product_code)
        # Check taxes and amounts
        self.assertEqual(invoice_line.invoice_line_tax_ids.mapped('code'), ['PVM1'])
        self.assertEqual(invoice_line.price_unit_tax_excluded, 44.62)
        self.assertEqual(invoice_line.price_unit_tax_included, 53.99)
        # Other base fields check for test coverage - not present in the remaining invoice creation tests
        self.assertEqual(invoice_line.name, product_name + ' Description')

    def test_04__create_order_eu_physical_partner_non_vat_payer(self):
        # Base test record names
        invoice_number, product_code, product_name, partner_name = \
            'RoboAPITestInvoiceNumber2', 'TP2', 'Test Product 2', 'Robo API Test Partner 2'

        post = {'due_date': self.invoice_date,
                'invoice_lines': [{'product': product_name, 'product_id': 1538, 'price': 44.6198345, 'qty': 2,
                                   'vat_code': 'PVM1', 'product_code': product_code, 'vat': 18.74,
                                   'description': product_name + ' Description'}], 'journal': 'RoboAPI',
                'number': invoice_number, 'date_invoice': self.invoice_date, 'currency': 'EUR',
                'secret': self.api_secret, 'payments': [{'date': self.invoice_date, 'amount': 107.98,
                                                         'payer': partner_name}],
                'partner': {'city': 'Test City', 'company_code': '', 'name': partner_name,
                            'zip': '123456', 'country': 'LV', 'phone': '123456789', 'street': 'Test Street',
                            'vat_code': '', 'email': 'testemail@gmail.com', 'is_company': False},
                'force_type': 'out_invoice'}

        base_method_name = at.API_METHOD_MAPPING.get('create_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the invoice should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(len(response.get('data')), 0)

        # Check partner to be physical
        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
        self.assertEqual(partner.country_id.code, 'LV')
        self.assertFalse(partner.is_company)

        # Check state and amounts
        invoice = self.env['account.invoice'].search([('number', '=', invoice_number)], limit=1)
        self.assertEqual(invoice.state, 'paid')
        self.assertTrue(invoice.price_include)
        self.assertFalse(invoice.has_outstanding)
        self.assertEqual(invoice.amount_total, 107.98)
        self.assertEqual(invoice.amount_tax, 0.0)
        self.assertEqual(invoice.amount_untaxed, 107.98)

        # Check invoice line
        invoice_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id.default_code == product_code)
        # Check taxes and amounts
        self.assertEqual(invoice_line.invoice_line_tax_ids.mapped('code'), ['Ne PVM'])
        self.assertEqual(invoice_line.price_unit_tax_excluded, 53.99)
        self.assertEqual(invoice_line.price_unit_tax_included, 53.99)

    def test_05__create_order_eu_juridical_partner_vat_payer(self):
        # Base test record names
        invoice_number, product_code, product_name, partner_name = \
            'RoboAPITestInvoiceNumber3', 'TP3', 'Test Product 3', 'Robo API Test Partner 3'

        post = {'due_date': self.invoice_date,
                'invoice_lines': [{'product': product_name, 'product_id': 1539, 'price': 53.99, 'qty': 2,
                                   'vat_code': 'PVM13', 'product_code': product_code, 'vat': 0.0,
                                   'description': product_name + ' Description'}], 'journal': 'RoboAPI',
                'number': invoice_number, 'date_invoice': self.invoice_date, 'currency': 'EUR',
                'secret': self.api_secret, 'payments': [{'date': self.invoice_date, 'amount': 107.98,
                                                         'payer': partner_name}],
                'partner': {'city': 'Test City', 'company_code': '123456789', 'name': partner_name,
                            'zip': '123456', 'country': 'LV', 'phone': '123456789', 'street': 'Test Street',
                            'vat_code': 'LV12345678901', 'email': 'testemail@gmail.com', 'is_company': False},
                'force_type': 'out_invoice'}

        base_method_name = at.API_METHOD_MAPPING.get('create_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the invoice should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(len(response.get('data')), 0)

        # Check partner to be juridical
        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
        self.assertEqual(partner.country_id.code, 'LV')
        self.assertTrue(partner.is_company)

        # Check invoice
        invoice = self.env['account.invoice'].search([('number', '=', invoice_number)], limit=1)
        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.price_include)
        self.assertFalse(invoice.has_outstanding)
        self.assertEqual(invoice.amount_total, 107.98)
        self.assertEqual(invoice.amount_tax, 0.0)
        self.assertEqual(invoice.amount_untaxed, 107.98)

        # Check invoice line
        invoice_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id.default_code == product_code)
        # Check taxes and amounts
        self.assertEqual(invoice_line.invoice_line_tax_ids.mapped('code'), ['PVM13'])
        self.assertEqual(invoice_line.price_unit_tax_excluded, 53.99)
        self.assertEqual(invoice_line.price_unit_tax_included, 53.99)

    def test_06__create_order_eu_juridical_partner_non_vat_payer(self):
        # Base test record names
        invoice_number, product_code, product_name, partner_name = \
            'RoboAPITestInvoiceNumber4', 'TP4', 'Test Product 4', 'Robo API Test Partner 4'

        post = {'due_date': self.invoice_date,
                'invoice_lines': [{'product': product_name, 'product_id': 1539, 'price': 53.99, 'qty': 2,
                                   'vat_code': 'PVM13', 'product_code': product_code, 'vat': 0.0,
                                   'description': product_name + ' Description'}], 'journal': 'RoboAPI',
                'number': invoice_number, 'date_invoice': self.invoice_date, 'currency': 'EUR',
                'secret': self.api_secret, 'payments': [{'date': self.invoice_date, 'amount': 107.98,
                                                         'payer': partner_name}],
                'partner': {'city': 'Test City', 'company_code': '123456789', 'name': partner_name,
                            'zip': '123456', 'country': 'LV', 'phone': '123456789', 'street': 'Test Street',
                            'vat_code': '', 'email': 'testemail@gmail.com', 'is_company': False},
                'force_type': 'out_invoice'}

        base_method_name = at.API_METHOD_MAPPING.get('create_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the invoice should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(len(response.get('data')), 0)

        # Check partner to be juridical
        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
        self.assertEqual(partner.country_id.code, 'LV')
        self.assertTrue(partner.is_company)

        # Check invoice
        invoice = self.env['account.invoice'].search([('number', '=', invoice_number)], limit=1)
        # Check state and amounts
        self.assertEqual(invoice.state, 'paid')
        self.assertTrue(invoice.price_include)
        self.assertFalse(invoice.has_outstanding)
        self.assertEqual(invoice.amount_total, 107.98)
        self.assertEqual(round(invoice.amount_tax, 2), 18.74)
        self.assertEqual(invoice.amount_untaxed, 89.24)

        # Check invoice line
        invoice_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id.default_code == product_code)
        # Check taxes and amounts
        self.assertEqual(invoice_line.invoice_line_tax_ids.mapped('code'), ['PVM1'])
        self.assertEqual(invoice_line.price_unit_tax_excluded, 44.62)
        self.assertEqual(invoice_line.price_unit_tax_included, 53.99)

    def test_07__create_order_eu_physical_partner_vat_payer(self):
        # Base test record names
        invoice_number, product_code, product_name, partner_name = \
            'RoboAPITestInvoiceNumber5', 'TP5', 'Test Product 5', 'Robo API Test Partner 5'

        post = {'due_date': self.invoice_date,
                'invoice_lines': [{'product': product_name, 'product_id': 1538, 'price': 44.6198345, 'qty': 2,
                                   'vat_code': 'PVM1', 'product_code': product_code, 'vat': 18.74,
                                   'description': product_name + ' Description'}], 'journal': 'RoboAPI',
                'number': invoice_number, 'date_invoice': self.invoice_date, 'currency': 'EUR',
                'secret': self.api_secret, 'payments': [{'date': self.invoice_date, 'amount': 107.98,
                                                         'payer': partner_name}],
                'partner': {'city': 'Test City', 'company_code': '', 'name': partner_name,
                            'zip': '123456', 'country': 'LV', 'phone': '123456789', 'street': 'Test Street',
                            'vat_code': 'LV12345678910', 'email': 'testemail@gmail.com', 'is_company': False},
                'force_type': 'out_invoice'}

        base_method_name = at.API_METHOD_MAPPING.get('create_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - the invoice should be created
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertEqual(len(response.get('data')), 0)

        # Check partner to be physical
        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
        self.assertEqual(partner.country_id.code, 'LV')
        self.assertFalse(partner.is_company)

        # Check state and amounts
        invoice = self.env['account.invoice'].search([('number', '=', invoice_number)], limit=1)
        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.price_include)
        self.assertFalse(invoice.has_outstanding)
        self.assertEqual(invoice.amount_total, 107.98)
        self.assertEqual(invoice.amount_tax, 0.0)
        self.assertEqual(invoice.amount_untaxed, 107.98)

        # Check invoice line
        invoice_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id.default_code == product_code)
        # Check taxes and amounts
        self.assertEqual(invoice_line.invoice_line_tax_ids.mapped('code'), ['PVM13'])
        self.assertEqual(invoice_line.price_unit_tax_excluded, 53.99)
        self.assertEqual(invoice_line.price_unit_tax_included, 53.99)

    def test_08__get_invoice(self):
        invoice_number = 'RoboAPITestInvoiceNumber1'
        post = {'secret': self.api_secret, 'invoice_number': invoice_number}

        base_method_name = at.API_METHOD_MAPPING.get('get_invoice')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - invoice should be found
        self.assertEqual(str(response.get('error')), 'Invoice was found in the system.')
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        self.assertNotEqual(len(response.get('data')), 0)

    def test_09__get_created_categories(self):
        post = {'secret': self.api_secret, 'execute_immediately': True}

        base_method_name = at.API_METHOD_MAPPING.get('product_categories')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - a list of product categories should be returned
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        data_is_returned = len(response.get('data')) != 0
        self.assertTrue(data_is_returned)

    def test_10__get_created_products(self):
        date_dt = datetime.today()
        # Approximate period
        date_from = (date_dt + relativedelta(minutes=-2)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to = (date_dt + relativedelta(minutes=2)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        post = {'secret': self.api_secret, 'date_from': date_from,
                'date_to': date_to, 'data_type': 'modify', 'execute_immediately': True}

        base_method_name = at.API_METHOD_MAPPING.get('new_products')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - a list of products should be returned
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        data_is_returned = len(response.get('data')) != 0
        self.assertTrue(data_is_returned)

    def test_11__get_products_in_stock(self):
        post = {'secret': self.api_secret, 'warehouse': 'WH', 'execute_immediately': True}

        base_method_name = at.API_METHOD_MAPPING.get('products')
        api_method = getattr(self.RoboApiBase, base_method_name)
        response = api_method(post)

        # Check the returned response - a list of products should be returned
        self.assertEqual(str(response.get('error')), str())
        self.assertEqual(response.get('code'), 200)
        self.assertEqual(response.get('system_error'), str())
        data_is_returned = len(response.get('data')) != 0
        self.assertTrue(data_is_returned)
