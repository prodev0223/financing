# -*- encoding: utf-8 -*-
from __future__ import division

import json

import requests

from odoo import models, api, tools, _, exceptions
import base64
from datetime import datetime
from .. import robo_api_tools as at
import logging
import re

_logger = logging.getLogger(__name__)

LANGUAGE_MAPPING = {
    'LT': 'lt_LT',
    'EN': 'en_US',
}


def check_date_format(date, field_name):
    error_message = str()
    try:
        datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
    except (ValueError, TypeError):
        try:
            datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        except (ValueError, TypeError):
            error_message = 'Incorrect date format of field "%s". Expected format - YYYY-MM-DD.' % field_name
    return error_message


def check_datetime_format(date, field_name):
    error_message = str()
    try:
        datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
    except (ValueError, TypeError):
        error_message = 'Incorrect date format of field "%s". Expected format - YYYY-MM-DD HH:MM:SS.' % field_name
    return error_message


def f_resp(code, error=str(), system_error=str(), data=None):
    """
    Format response message by zipping
    """
    data = [] if data is None else data
    return dict(zip(at.RESPONSE_STRUCTURE, [error, code, system_error, data]))


class RoboAPIBase(models.AbstractModel):
    """
    ! FUNCTIONALITY IS MOVED FROM robo_api controller!
    Would be nice to refactor these methods
    Used to hold executable methods for API endpoints
    """
    _name = 'robo.api.base'

    # Product API Endpoints -------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def api_create_product(self, post):
        """
        Create //
        API endpoint that is used to create product.product records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        product_template_obj = self.env['product.template'].sudo()
        account_tax_obj = self.env['account.tax'].sudo()
        ResCountry = self.env['res.country'].sudo()
        allow_empty = not self.env.user.sudo().company_id.prevent_empty_product_code

        product_name = (post.get('name') or '').strip()
        if not product_name:
            return f_resp(at.API_INCORRECT_DATA, 'Missing product name')
        product_code = (post.get('default_code') or '').strip()
        if not product_code and not allow_empty:
            return f_resp(at.API_INCORRECT_DATA, 'Missing product code')

        categ_id = post.get('categ_id')
        product_type = post.get('type', 'product')
        if not categ_id:
            if product_type == 'service':
                categ_id = self.env.ref('l10n_lt.product_category_2').id
            else:
                categ_id = self.env.ref('l10n_lt.product_category_1').id

        price = post.get('price')
        sync_price = int(post.get('sync_price', '0'))
        barcode = post.get('barcode')
        if barcode:
            existing_barcode = self.env['product.product'].sudo().search_count([('barcode', '=', barcode)])
            if existing_barcode:
                return f_resp(at.API_INCORRECT_DATA,
                              'Product with this barcode ({}) already exists, barcode needs to be unique'.format(
                                  barcode))
        try:
            vat_code = post.get('vat_code')
            tax = account_tax_obj.search([('code', '=', vat_code),
                                          ('type_tax_use', '=', 'sale'),
                                          ('price_include', '=', False),
                                          ('nondeductible', '=', False)])
            if not tax:
                return f_resp(at.API_INCORRECT_DATA, 'Could not find VAT with provided code ({})'.format(vat_code))
        except KeyError:
            return f_resp(at.API_INCORRECT_DATA, 'vat_code not provided')
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_NOT_FOUND, 'Could not find VAT', system_error)

        product_vals = {
            'name': product_name,
            'default_code': product_code,
            'type': product_type,
            'sale_ok': True,
            'purchase_ok': False,
            'taxes_id': [(4, tax.id)],
            'categ_id': categ_id,
            'list_price': price,
            'barcode': barcode,
        }

        # Intrastat-related data
        report_intrastat_code, error_str = self.find_or_create_intrastat_code(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        if report_intrastat_code:
            product_vals['intrastat_id'] = report_intrastat_code.id

        product_intrastat_description = (post.get('product_intrastat_description') or '').strip()
        if product_intrastat_description:
            product_vals['intrastat_description'] = product_intrastat_description
        origin_country_code = (post.get('origin_country') or '').strip()
        if origin_country_code:
            origin_country = ResCountry.search([('code', '=', origin_country_code)], limit=1)
            if not origin_country:
                return f_resp(at.API_INCORRECT_DATA, 'Could not determine product origin country')
            product_vals['kilmes_salis'] = origin_country.id

        raso_installed = bool(self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'raso_retail'), ('state', 'in', ['installed', 'to upgrade'])]))
        if raso_installed:
            importable_to_raso = self.env['product.category'].sudo().browse(categ_id).importable_to_raso
            if importable_to_raso:
                if not barcode:
                    return f_resp(at.API_INCORRECT_DATA, 'Barcode is required')
                if round(tax.amount) not in at.RASO_VATRATE_TO_VATCODE_MAPPER.keys():
                    return f_resp(at.API_INCORRECT_DATA, 'Tax rate can only be 0, 5 or 21%')
            if sync_price and not importable_to_raso:
                return f_resp(at.API_INCORRECT_DATA, 'The product is not importable to Raso. Sync is not possible')
            if importable_to_raso and sync_price:
                if 'price_with_vat' not in post:
                    return f_resp(at.API_INCORRECT_DATA, 'To sync prices, you need to specify price_with_vat')
                price_with_vat = float(post['price_with_vat'])
                value_to_compare = abs(price_with_vat - price * (1 + tax.amount / 100.0))  # P3:DivOK
                if tools.float_compare(value_to_compare, 0.01, precision_digits=2) > 0:
                    return f_resp(at.API_INCORRECT_DATA, 'price, price_with_vat and vat_code do not match.')
                product_vals['vat_code'] = at.RASO_VATRATE_TO_VATCODE_MAPPER[int(round(tax.amount))]

        try:
            product = product_template_obj.with_context(raso_bypass_listprice_sync=True).create(product_vals)
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'The product could not be created', system_error)

        if sync_price and raso_installed and product.importable_to_raso:
            price_with_vat = float(post['price_with_vat'])
            self.env['product.template.prices'].sudo().create({
                'product_id': product.id,
                'price': price_with_vat,
                'qty': 1.0,
            })

        return f_resp(at.API_SUCCESS)

    @api.model
    def api_update_product(self, post):
        """
        Update //
        API endpoint that is used to update product.product records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        AccountTax = self.env['account.tax'].sudo()
        ProductProduct = self.env['product.product'].sudo()
        ProductCategory = self.env['product.category'].sudo()
        ResCountry = self.env['res.country'].sudo()

        product_id = post['product_id'] if type(post['product_id']) == int else False
        if not product_id:
            return f_resp(at.API_INCORRECT_DATA, 'Missing product identification information')

        product = ProductProduct.search([('id', '=', product_id), ('categ_id.skip_api_sync', '=', False)])
        if not product:
            return f_resp(at.API_NOT_FOUND, 'Product with id {} not found'.format(product_id))

        product_vals = {}
        if 'default_code' in post and post['default_code']:
            product_code = post.get('default_code').strip()
            existing = ProductProduct.search_count([('default_code', '=', product_code),
                                                    ('id', '!=', product.id)])
            if existing:
                return f_resp(at.API_INCORRECT_DATA, 'Product with code "{}" already exists.'.format(product_code))
            product_vals['default_code'] = product_code
        if 'name' in post and post['name']:
            product_name = post.get('name').strip()
            existing = ProductProduct.with_context(lang='lt_LT').search_count([('name', '=', product_name),
                                                                               ('id', '!=', product.id)])
            if not existing:
                existing = ProductProduct.with_context(lang='en_US').search_count([('name', '=', product_name),
                                                                                   ('id', '!=', product.id)])
            if existing:
                return f_resp(at.API_INCORRECT_DATA, 'Product with name "{}" already exists.'.format(product_name))
            product_vals['name'] = product_name
        if 'categ_id' in post:
            categ_id = post['categ_id'] if type(post['categ_id']) == int else False
            if not categ_id:
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect category value')
            product_category = ProductCategory.search([('id', '=', categ_id)])
            if not product_category:
                return f_resp(at.API_NOT_FOUND, 'Product category with provided ID ({}) not found'.format(categ_id))
            product_vals['categ_id'] = product_category.id

        if 'type' in post and post['type']:
            product_type = post.get('type').strip()
            if product_type not in ['product', 'service']:
                return f_resp(at.API_INCORRECT_DATA, 'Product type must be one of the following: product, service.')
            product_vals['type'] = product_type

        if 'price' in post:
            price = float(post['price']) if type(post.get('price')) in [float, int, long] else False
            if not price:
                return f_resp(at.API_INCORRECT_DATA, 'Wrong price value')
            product_vals['list_price'] = price

        if 'barcode' in post and post['barcode']:
            barcode = post.get('barcode').strip()
            existing = ProductProduct.sudo().search_count([('barcode', '=', barcode),
                                                           ('id', '!=', product.id)])
            if existing:
                return f_resp(at.API_INCORRECT_DATA,
                              'Product with barcode "{}" already exists, barcode needs to be unique'.format(
                                  barcode))
            product_vals['barcode'] = barcode

        if 'vat_code' in post and post['vat_code']:
            vat_code = post.get('vat_code').strip()
            tax = AccountTax.search([('code', '=', vat_code),
                                     ('type_tax_use', '=', 'sale'),
                                     ('price_include', '=', False),
                                     ('nondeductible', '=', False)], limit=1)
            if not tax:
                return f_resp(at.API_NOT_FOUND, 'Could not find VAT with provided code %s' % vat_code)
            product_vals['taxes_id'] = [(6, 0, tax.ids)]

        # Intrastat-related data
        report_intrastat_code, error_str = self.find_or_create_intrastat_code(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        if report_intrastat_code:
            product_vals['intrastat_id'] = report_intrastat_code.id

        product_intrastat_description = (post.get('product_intrastat_description') or '').strip()
        if product_intrastat_description:
            product_vals['intrastat_description'] = product_intrastat_description
        origin_country_code = (post.get('origin_country') or '').strip()
        if origin_country_code:
            origin_country = ResCountry.search([('code', '=', origin_country_code)], limit=1)
            if not origin_country:
                return f_resp(at.API_INCORRECT_DATA,
                              'Could not determine product origin country with provided code ({})'.
                              format(origin_country_code))
            product_vals['kilmes_salis'] = origin_country.id

        try:
            product.with_context(raso_bypass_listprice_sync=True).write(product_vals)
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'The product could not be updated', system_error)

        return f_resp(at.API_SUCCESS)

    @api.model
    def api_write_off_products(self, post):
        """
        Create //
        API endpoint that is used to create stock.inventory records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        StockInventory = self.env['stock.inventory'].sudo()
        ProductProduct = self.env['product.product'].sudo()
        StockInventoryLine = self.env['stock.inventory.line'].sudo()
        vals = {'filter': 'partial'}
        robo_stock_installed = bool(self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])]))
        if not robo_stock_installed:
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Stock module is not installed')

        name = post.get('name')
        if not name:
            return f_resp(at.API_INCORRECT_DATA, 'Missing name')
        vals.update({'name': name})

        warehouse_code = post.get('warehouse_code')
        if not warehouse_code:
            return f_resp(at.API_INCORRECT_DATA, 'Warehouse is missing')
        warehouse_id = self.env['stock.warehouse'].search([('code', '=', warehouse_code)])
        if not warehouse_id:
            return f_resp(at.API_INCORRECT_DATA, 'Warehouse with provided code (%s) was not found' % warehouse_code)
        if len(warehouse_id) > 1:
            return f_resp(at.API_INCORRECT_DATA, 'More than one warehouse was found by this code (%s)' % warehouse_code)
        if not warehouse_id.lot_stock_id:
            return f_resp(at.API_INCORRECT_DATA, 'Warehouse with provided code (%s) does not have a location')
        location_id = warehouse_id.lot_stock_id
        vals.update({'location_id': location_id.id})

        committee = post.get('committee')
        if not committee:
            return f_resp(at.API_INCORRECT_DATA, 'Missing committee')
        committee_id = self.env['alignment.committee'].search([('name', '=', committee),
                                                               ('state', '=', 'valid'),
                                                               ('type', '=', 'inventory')])
        if not committee_id:
            return f_resp(at.API_INCORRECT_DATA,
                          'Alignment committee with provided name (%s) was not found' % committee)
        vals.update({'komisija': committee_id.id})

        accounting_date = post.get('accounting_date')
        if not accounting_date:
            return f_resp(at.API_INCORRECT_DATA, 'Missing accounting date')
        vals.update({'accounting_date': accounting_date})

        reason_line = post.get('reason_line')
        if not reason_line:
            return f_resp(at.API_INCORRECT_DATA, 'Missing reason line')
        reason_line_id = self.env['stock.reason.line'].search([('name', '=', reason_line)])
        if not reason_line_id:
            return f_resp(at.API_INCORRECT_DATA, 'Reason with provided name (%s) was not found' % reason_line)
        vals.update({'reason_line': reason_line_id.id})

        account_id = reason_line_id.account_id
        account_code = post.get('account_code')
        if account_code:
            account_id = self.env['account.account'].search([('code', '=', account_code)])
        if not account_id:
            return f_resp(at.API_INCORRECT_DATA, 'Account with provided code (%s) was not found' % account_code)
        vals.update({'account_id': account_id.id})

        analytic_code = post.get('analytic_code')
        if analytic_code:
            analytic_account_id = self.env['account.analytic.account'].search([('code', '=', analytic_code)])
            if not analytic_account_id:
                return f_resp(at.API_INCORRECT_DATA,
                              'Analytic account with provided code (%s) was not found' % analytic_code)
            vals.update({'account_analytic_id': analytic_account_id.id})

        products = post.get('products')
        if not products:
            return f_resp(at.API_INCORRECT_DATA, 'Missing products')

        try:
            inventory_id = StockInventory.create(vals)
            inventory_id.prepare_inventory()
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Stock inventory can not be created', system_error)

        for product in products:
            product_code = product.get('code')
            if not product_code:
                return f_resp(at.API_INCORRECT_DATA, 'Missing product code')
            product_id = ProductProduct.search([('default_code', '=', product_code)], limit=1)
            if not product_id:
                return f_resp(at.API_INCORRECT_DATA, 'Product with provided code (%s) was not found' % product_code)

            try:
                stock_inventory_line_id = StockInventoryLine.create({'product_id': product_id.id,
                                                                     'location_id': location_id.id,
                                                                     'inventory_id': inventory_id.id})
            except Exception as e:
                system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
                _logger.info(system_error)
                return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Stock inventory line can not be created', system_error)

            consumed_qty = product.get('consumed_qty')
            if not consumed_qty:
                consumed_qty = -abs(stock_inventory_line_id.theoretical_qty)
            stock_inventory_line_id.write({'consumed_qty': consumed_qty})

        try:
            inventory_id.button_action_done()
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Stock inventory can not be validated', system_error)

        return f_resp(at.API_SUCCESS)

    @api.model
    def api_get_products_by_date(self, post):
        """
        Get //
        API endpoint that is used to fetch product.product records by date
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        date_from = post.get('date_from')
        date_to = post.get('date_to')
        data_type = post.get('data_type', 'create')
        if not date_from or not date_to:
            return f_resp(at.API_INCORRECT_DATA, 'At least one of date_from or date_to must be provided.')
        error_str = check_datetime_format(date_from, 'date_from')
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        error_str = check_datetime_format(date_to, 'date_to')
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        product_data = []
        product_obj = self.env['product.product'].sudo()
        domain = [('robo_product', '=', False), ('categ_id.skip_api_sync', '=', False)]
        if data_type == 'create':
            domain += [('create_date', '<=', date_to), ('create_date', '>=', date_from)]
        elif data_type == 'modify':
            domain += [('write_date', '<=', date_to), ('write_date', '>=', date_from)]
        else:
            return f_resp(at.API_INCORRECT_DATA, 'Data type should be "create" or "modify"')
        for product_id in product_obj.search(domain):
            product_data.append({
                'product_id': product_id.id,
                'name': product_id.name,
                'code': product_id.default_code,
                'barcode': product_id.barcode,
                'image': product_id.image_medium,
                'default_sale_taxes': product_id.mapped('taxes_id.code'),
                'default_purchase_taxes': product_id.mapped('supplier_taxes_id.code'),
                'category_id': product_id.categ_id.id,
                'type': product_id.type,
                'public_price': product_id.list_price,
                'date_create': product_id.create_date
            })
        message = str()
        if not product_data:
            message = 'No products were found!'
            status_code = at.API_NOT_FOUND
        else:
            status_code = at.API_SUCCESS
        return f_resp(status_code, message, data=product_data)

    @api.model
    def api_get_products_by_wh(self, post):
        """
        Get //
        API endpoint that is used to fetch product.product records by warehouse
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        warehouse = post.get('warehouse', 'WH')
        warehouse_id = self.env['stock.warehouse'].sudo().search([('code', '=', warehouse)], limit=1)
        if not warehouse_id:
            return f_resp(at.API_NOT_FOUND, 'Warehouse {} not found.'.format(warehouse))
        product_obj = self.env['product.product'].sudo()
        domain = [('type', '=', 'product'), ('robo_product', '=', False), ('categ_id.skip_api_sync', '=', False)]
        product_data = product_obj.search(domain).with_context(
            warehouse=warehouse_id.id).mapped(lambda r: {
            'product_id': r.id,
            'name': r.name,
            'code': r.default_code,
            'barcode': r.barcode,
            'qty_on_hand': r.qty_available,
            'qty_forecasted': r.virtual_available,
            'public_price': r.list_price,
            'category_id': r.categ_id.id,
            'avg_cost': r.avg_cost})

        message = str()
        if not product_data:
            message = 'No products were found!'
            status_code = at.API_NOT_FOUND
        else:
            status_code = at.API_SUCCESS
        return f_resp(status_code, message, data=product_data)

    # Product category API Endpoints ----------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def api_create_product_category(self, post):
        """
        Create //
        API endpoint that is used to create product.category record
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        ResCategory = self.env['product.category'].sudo()
        category_name = (post.get('name') or '').strip()
        if not category_name:
            return f_resp(at.API_INCORRECT_DATA, 'Category name is required.')

        existing = ResCategory.with_context(lang='lt_LT').search_count([('name', '=', category_name)])
        if not existing:
            existing = ResCategory.with_context(lang='en_US').search_count([('name', '=', category_name)])
        if existing:
            return f_resp(at.API_INCORRECT_DATA, 'Category with this name ({}) already exists.'.format(category_name))
        category_type = (post.get('type') or '').strip()
        if not category_type:
            return f_resp(at.API_INCORRECT_DATA, 'Category type is required.')
        if category_type not in ['products', 'services', 'cost_adjustments']:
            return f_resp(at.API_INCORRECT_DATA,
                          'Category type must be one of the following: products, services or cost_adjustments.')

        category_values = {
            'name': category_name,
            'accounting_category_type': category_type,
            'acc_product_type': 'product' if category_type == 'products' else 'service'
        }

        # Intrastat-related data
        report_intrastat_code, error_str = self.find_or_create_intrastat_code(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        if report_intrastat_code:
            category_values['intrastat_id'] = report_intrastat_code.id

        try:
            category = ResCategory.create(category_values)
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'The category could not be created', system_error)
        return f_resp(at.API_SUCCESS, data={'id': category.id})

    @api.model
    def api_get_product_categories(self, *_):
        """
        Get //
        API endpoint that is used to return product.category data
        :return: response text, response code
        """

        # Gather category data
        categ_data = []
        for category in self.env['product.category'].sudo().search(
                [('robo_category', '=', False), ('accounting_category_type', '=', 'products')]):
            categ_data.append({
                'name': category.name,
                'id': category.id,
            })
        message = str()
        if not categ_data:
            message = 'No categories were found!'
            status_code = at.API_NOT_FOUND
        else:
            status_code = at.API_SUCCESS
        return f_resp(status_code, message, data=categ_data)

    @api.model
    def api_update_product_category(self, post):
        """
        Update //
        API endpoint that is used to update product.category record
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        ResCategory = self.env['product.category'].sudo()
        category_id = post['categ_id'] if 'categ_id' in post and type(post['categ_id']) == int else False
        if not category_id:
            return f_resp(at.API_INCORRECT_DATA, 'Missing category identification information')

        category_vals = {}
        # Do not use browse with random value (or use browse().exists()), because it always finds a record
        # no matter what int you pass (env['product.product'].browse(9999))
        category = ResCategory.search([('id', '=', category_id), ('skip_api_sync', '=', False)])

        if not category:
            return f_resp(at.API_NOT_FOUND, 'Category with provided ID ({}) not found'.format(category_id))

        if 'name' in post and post['name']:
            category_name = post.get('name').strip()
            existing = ResCategory.with_context(lang='lt_LT').search_count([('name', '=', category_name),
                                                                            ('id', '!=', category.id)])
            if not existing:
                existing = ResCategory.with_context(lang='en_US').search_count([('name', '=', category_name),
                                                                                ('id', '!=', category.id)])
            if existing:
                return f_resp(at.API_INCORRECT_DATA, 'Category with provided name ({}) already exists.'.
                              format(category_name))
            category_vals['name'] = category_name

        if 'type' in post and post['type']:
            category_type = post.get('type').strip()
            if category_type not in ['products', 'services', 'cost_adjustments']:
                return f_resp(at.API_INCORRECT_DATA,
                              'Category type must be one of the following: products, services or cost_adjustments.')
            category_vals['accounting_category_type'] = category_type
            category_vals['acc_product_type'] = 'product' if category_type == 'products' else 'service'

        # Intrastat-related data
        report_intrastat_code, error_str = self.find_or_create_intrastat_code(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        if report_intrastat_code:
            category_vals['intrastat_id'] = report_intrastat_code.id

        try:
            category.write(category_vals)
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'The category could not be updated', system_error)
        return f_resp(at.API_SUCCESS)

    # Invoice API Endpoints -------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def api_create_invoice(self, post):
        """
        Create //
        API endpoint that is used to create account.invoice records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """

        company = self.env.user.sudo().company_id
        api_force_global_tax = company.api_force_tax_id if company.api_force_tax_selection == 'global' else False
        api_ft_condition = company.api_force_tax_condition
        api_woocommerce = company.api_woocommerce_integration
        api_rounding_error = company.api_max_rounding_error_allowed if company.api_allow_rounding_error else 0.0

        # Objects
        invoice_obj = self.env['account.invoice']
        currency_obj = self.env['res.currency']
        journal_obj = self.env['account.journal']
        account_obj = self.env['account.account']
        bclass_obj = self.env['b.klase.kodas']
        stock_location_obj = self.env['stock.location']
        stock_warehouse_obj = self.env['stock.warehouse']
        ForceTaxPosition = self.env['robo.api.force.tax.position']

        robo_stock_installed = bool(self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])]))
        extended_stock = robo_stock_installed and company.politika_sandelio_apskaita == 'extended'
        date_inv = post.get('date_invoice', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        error_str = check_date_format(date_inv, 'date_invoice')
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        # Get clients vat payer status
        vat_payer = company.with_context(date=date_inv).vat_payer

        invoice_vals = {
            'skip_isaf': post.get('skip_isaf', False),
            'date_invoice': date_inv,
            'operacijos_data': date_inv,
        }
        due_date = post.get('due_date')
        if due_date:
            error_str = check_date_format(due_date, 'due_date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            invoice_vals.update({
                'date_due': due_date,
                'payment_term_id': False,
            })
        warehouse_cost = post.get('warehouse_cost')
        if robo_stock_installed and warehouse_cost:
            invoice_vals.update({'warehouse_cost': warehouse_cost})
        registration_date = post.get('registration_date')
        if registration_date:
            error_str = check_date_format(registration_date, 'registration_date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            invoice_vals['registration_date'] = registration_date
        proforma = post.get('proforma', False)
        draft = post.get('draft', False)
        force_dates = post.get('force_dates', False)
        cancelled = post.get('cancelled', False)
        force_type = post.get('force_type', False)
        currency_id = False
        if 'currency' in post:
            currency_id = currency_obj.search([('name', '=', post['currency'])], limit=1)
        if currency_id:
            invoice_vals['currency_id'] = currency_id.id
            if currency_id != company.currency_id and not (draft or proforma or cancelled):
                if datetime.strptime(date_inv, tools.DEFAULT_SERVER_DATE_FORMAT).date() > datetime.utcnow().date():
                    return f_resp(at.API_INCORRECT_DATA,
                                  'Invoice not in company currency cannot be validated at future dates')
        else:
            return f_resp(at.API_INCORRECT_DATA, 'Incorrect currency')
        if not draft or 'payments' in post:
            if 'number' not in post or not post['number']:
                return f_resp(at.API_INCORRECT_DATA, 'Missing invoice number')
            if invoice_obj.search([('number', '=', post['number'])], count=True):
                return f_resp(at.API_INCORRECT_DATA, 'Invoice with %s number already exists.' % post['number'])
        if 'partner' not in post or not post['partner']:
            return f_resp(at.API_INCORRECT_DATA, 'Missing partner info')
        if 'journal' not in post or not post['journal']:
            return f_resp(at.API_INCORRECT_DATA, 'Missing journal info')
        if ('supplier_invoice' in post and post['supplier_invoice']) or \
                (force_type and force_type in ['in_invoice', 'in_refund']):
            supplier_invoice = True
        else:
            supplier_invoice = False
        journal_code = post['journal']
        journal_type = 'purchase' if supplier_invoice else 'sale'
        journal_id = journal_obj.search([('code', '=', journal_code), ('type', '=', journal_type)], limit=1)
        if not journal_id:
            journal_id = journal_obj.create({
                'name': journal_code,
                'code': journal_code,
                'type': journal_type,
            })
        if journal_id:
            invoice_vals['journal_id'] = journal_id.id
        else:
            return f_resp(at.API_INCORRECT_DATA, 'Failed creating invoice series because journal info is invalid')
        partner, error_str = self.find_or_create_partner(post['partner'])
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        invoice_reference = (post.get('reference', str()) or post.get('number', str())).strip()
        if supplier_invoice and invoice_reference and ' ' in invoice_reference:
            return f_resp(at.API_INCORRECT_DATA, 'Supplier invoice number cannot contain spaces')
        invoice_exists = invoice_obj.search_count([
            ('partner_id', '=', partner.id),
            ('type', 'in', ['in_invoice', 'in_refund']),
            ('reference', '=', invoice_reference),
        ])
        if invoice_exists:
            return f_resp(at.API_INCORRECT_DATA, 'Invoice for this partner with same reference number already exists')
        code = '4430' if supplier_invoice else '2410'
        account_id = account_obj.search([('code', '=', code)])
        if account_id:
            invoice_vals['account_id'] = account_id.id
        if not post.get('invoice_lines'):
            return f_resp(at.API_INCORRECT_DATA, 'Missing invoice lines')
        invoice_vals['partner_id'] = partner.id
        invoice_lines = []
        invoice_vals['invoice_line_ids'] = invoice_lines
        total_tax = 0.0
        total_wo_amount = 0.0
        all_prices_wo_vat = True
        try:
            control_subtotal = float(post.get('subtotal', 0.0))
        except (ValueError, KeyError, TypeError):
            control_subtotal = 0.0
        total_is_provided = 'total' in post and post['total']
        woocommerce_control_total = 0.0
        force_type = post.get('force_type', False)
        negative = positive = abs_prices = prices_with_vat = False

        for line in post['invoice_lines']:
            try:
                price = float(line.get('price', 0.0))
            except (ValueError, KeyError, TypeError):
                price = 0.0
            if not price:
                try:
                    price = float(line.get('price_with_vat', 0.0))
                except (ValueError, KeyError, TypeError):
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')
            if price < 0.0 and not negative:
                negative = True
            if price > 0.0 and not positive:
                positive = True

        inv_types = ['in_invoice', 'in_refund', 'out_invoice', 'out_refund']
        if force_type and force_type in inv_types:
            if force_type in ['out_refund', 'in_refund'] and negative and positive:
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')
            if force_type in ['out_refund', 'in_refund'] and negative and not positive:
                abs_prices = True
            invoice_type = force_type
        else:
            if control_subtotal < 0.0:
                invoice_type = 'in_refund' if supplier_invoice else 'out_refund'
                control_subtotal = abs(control_subtotal)
                abs_prices = True
            elif control_subtotal > 0.0:
                invoice_type = 'in_invoice' if supplier_invoice else 'out_invoice'
            else:
                if negative and not positive:
                    invoice_type = 'in_refund' if supplier_invoice else 'out_refund'
                    abs_prices = True
                else:
                    invoice_type = 'in_invoice' if supplier_invoice else 'out_invoice'

        for line in post['invoice_lines']:
            product_id, error_str = self.find_or_create_product(line)
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)

            product = (line.get('product') or '').strip()
            description = (line.get('description') or '').strip()
            description = description if len(description) <= 200 else ''
            if 'qty' not in line or not isinstance(line['qty'], tuple([int, float, long])):
                if 'qty' in line:
                    try:
                        qty_converted = float(line['qty'])
                        line['qty'] = qty_converted
                    except ValueError:
                        return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty field.')
                else:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty field.')

            no_price = no_price_vat = False
            # Try to get price with VAT
            try:
                price_converted = float(line['price_with_vat'])
                line['price_with_vat'] = price_converted
            except (ValueError, KeyError):
                no_price_vat = True

            # Try to get price
            try:
                price_converted = float(line['price'])
                line['price'] = price_converted
            except (ValueError, KeyError):
                no_price = True

            # If price and price with vat does not exist, raise an error
            if no_price and no_price_vat:
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')

            # Try to convert vat rate
            try:
                vat_converted = float(line['vat'])
                line['vat'] = vat_converted
            except (ValueError, KeyError):
                pass

            # Try to get discount
            try:
                discount = abs(float(line['discount']))
                # Check for percentage
                if discount < 0 or discount > 100:
                    return f_resp(at.API_INCORRECT_DATA,
                                  'Incorrect invoice line discount field, value must be between 0 and 100.')
                line['discount'] = discount
            except (ValueError, KeyError, TypeError):
                line['discount'] = 0.0

            tax_ids = []
            # Check whether forced API taxes would be applied
            apply_api_ft = not supplier_invoice and api_woocommerce \
                           and api_ft_condition in ['force_if_none', 'force_on_gaps'] and vat_payer
            # If call is from WooCommerce, check tax forcing conditions:
            if apply_api_ft:
                if api_force_global_tax:
                    # Shipping always has vat/vat_code specified in plugin so
                    # an explicit check is needed when applying tax
                    is_shipping = line.get('product', str()) == 'Shipping'
                    # If forced taxes condition is 'force_if_none' and
                    # forced taxes would be applied -- no vat can be passed
                    if line.get('vat') and api_ft_condition == 'force_if_none' and not is_shipping:
                        return f_resp(at.API_INCORRECT_DATA, 'VAT amount was specified for order from WooCommerce.')

                    # Otherwise, apply taxes if no vat rate/zero vat rate or no vat_code is passed,
                    # or it is a shipping line
                    elif not line.get('vat') or not line.get('vat_code') or is_shipping:
                        # Reset VAT amount if vat code does not match the forced tax code or if the forced tax has VAT
                        # price included
                        if not line.get('vat_code') or line.get('vat_code') != api_force_global_tax.code or \
                                api_force_global_tax.price_include:
                            line.pop('vat', False)

                        tax_ids = api_force_global_tax.ids
                        line['vat_code'] = api_force_global_tax.code
                        if api_force_global_tax.price_include:
                            if 'price' in line:
                                # Act like price with VAT was specified
                                line['price_with_vat'] = line.pop('price')
                                no_price_vat = False
                else:
                    api_force_tax = ForceTaxPosition.get_tax_of_position_applied(partner.id, date_inv,
                                                                                 product_id.acc_product_type)
                    if api_force_tax:
                        tax_ids = api_force_tax.ids
                        line['vat_code'] = api_force_tax.code
                        if api_force_tax.price_include:
                            if 'price' in line:
                                # Act like price with VAT was specified
                                try:
                                    # P3:DivOK
                                    line['price_with_vat'] = line.pop('price') + line.pop('vat', 0.0) / abs(line['qty'])
                                except ZeroDivisionError:
                                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty.')
                                no_price_vat = False
                # Total amount is not provided in WooCommerce - it needs to be calculated to check if amounts provided
                # in lines match with an invoice in the system
                line_qty = abs(line.get('qty', 0.0))
                if not total_is_provided:
                    woocommerce_control_total += line.get('price_with_vat', 0.0) * line_qty or \
                                                 (line.get('price', 0.0) * line_qty + line.get('vat', 0.0))

            account_code = (line.get('account_code') or '').strip()
            if account_code:
                product_account = account_obj.search([('code', '=', account_code)], limit=1)
                if not product_account:
                    return f_resp(at.API_NOT_FOUND,
                                  'Account of code %s not found for invoice line.' % account_code)
            elif not supplier_invoice:
                product_account = product_id.get_product_income_account(return_default=True)
            else:
                product_account = product_id.get_product_expense_account(return_default=True)

            invoice_vat_code = line['vat_code'] if 'vat_code' in line else False
            if not invoice_vat_code and vat_payer and tools.float_compare(line.get('price', 0), 0.0,
                                                                          precision_digits=2) == 0:
                line['vat_code'] = invoice_vat_code = 'PVM1'

            if not invoice_vat_code and vat_payer:
                return f_resp(at.API_INCORRECT_DATA, 'Missing tax code')

            # If client is not VAT payer, and price with VAT is not provided, set price to be price with VAT
            if not vat_payer and no_price_vat:
                # Set price with VAT (already checked for existence and type before)
                line['price_with_vat'] = line.get('price')

            if 'price_with_vat' in line:
                prices_with_vat = True
                all_prices_wo_vat = False
            else:
                prices_with_vat = False

            if vat_payer and not tax_ids:
                tax_ids = self.find_corresponding_taxes(line, supplier_invoice)
                if not tax_ids:
                    return f_resp(at.API_NOT_FOUND, 'Could not find tax code %s' % invoice_vat_code)

            invoice_vals['price_include_selection'] = 'inc' if prices_with_vat else 'exc'
            if prices_with_vat:
                if abs_prices:
                    line['price_with_vat'] = abs(line.get('price_with_vat', 0.0))
                line['price'] = line['price_with_vat']
                line.pop('vat', None)
            if abs_prices:
                line['price'] = abs(line.get('price', 0.0))
                line['qty'] = abs(line.get('qty', 0.0))

            total_wo_amount += (line['price'] * line['qty']) * (1.0 - line.get('discount', 0.0) / 100.0)
            line_vals = {
                'product_id': product_id.id,
                'name': description or product_id.partner_ref or product,
                'quantity': line['qty'],
                'price_unit': line['price'],
                'discount': line['discount'],
                'uom_id': self.env.ref('product.product_uom_unit').id,
                'account_id': product_account.id,
                'invoice_line_tax_ids': [(6, 0, tax_ids)]
            }

            deferred_data, error_str = self.get_deferred_data(line, invoice_type, product_account)
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            if deferred_data:
                line_vals.update(deferred_data)

            analytic_account, error_str = self.find_or_create_analytic_account(line)
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            if analytic_account:
                invoice_vals['account_analytic_id'] = analytic_account.id

            invoice_lines.append((0, 0, line_vals))
            if 'vat' in line and line['vat']:
                total_tax += line['vat']
        invoice_vals['type'] = invoice_type
        invoice_vals['intrastat_country_id'] = partner.country_id.id
        invoice_vals['imported_api'] = True
        invoice_vals['force_dates'] = force_dates
        if post.get('b_class_code', False) and force_type in ['in_invoice', 'in_refund']:
            b_class_id = bclass_obj.search([('code', '=', post.get('b_class_code', False))])
            if b_class_id:
                invoice_vals['b_klase_kodas_id'] = b_class_id.id

        language = post.get('language', 'LT')
        if language not in LANGUAGE_MAPPING:
            return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice language')
        invoice_vals['partner_lang'] = LANGUAGE_MAPPING[language]
        invoice_vals['comment'] = (post.get('comment') or '').strip()

        invoice_vals = self.add_extra_vals_overridable(invoice_vals, post)
        invoice_id = invoice_obj.create(invoice_vals)
        if not prices_with_vat and total_tax:
            tax_diff = abs(abs(invoice_id.amount_tax) - total_tax)
            if tools.float_compare(tax_diff, 0.05, precision_digits=2) > 0:
                return f_resp(
                    at.API_INCORRECT_DATA,
                    'Incorrect taxes. %s != %s' % (str(abs(invoice_id.amount_tax)), str(total_tax)))
            elif tools.float_compare(tax_diff, 0.0, precision_digits=2) > 0:
                invoice_id.write({
                    'force_taxes': True
                })
                amount_diff = abs(invoice_id.amount_tax) - total_tax
                if invoice_id.tax_line_ids:
                    invoice_id.tax_line_ids[0].amount -= amount_diff
        invoice_id.with_context(skip_vat_constrains=True).partner_data_force()
        # check total amounts
        if not control_subtotal:
            control_subtotal = total_wo_amount
        if all_prices_wo_vat:
            invoice_amount_total = sum(invoice_id.mapped('invoice_line_ids.price_subtotal'))
            if tools.float_compare(control_subtotal, invoice_amount_total, precision_digits=2) != 0:
                diff = control_subtotal - invoice_amount_total
                if tools.float_compare(abs(diff), 0.05, precision_digits=2) <= 0:
                    ch_invoice_line_id = invoice_id.invoice_line_ids[-1]
                    unit = (ch_invoice_line_id.price_unit * ch_invoice_line_id.quantity + diff) / \
                           ch_invoice_line_id.quantity  # P3:DivOK
                    ch_invoice_line_id.price_unit = unit
                else:
                    msg = 'Invoice subtotal amounts do not match (%s != %s). Contact administrator.' % (
                        control_subtotal, invoice_amount_total)
                    _logger.info('ROBO API: ' + msg)
                    return f_resp(at.API_INCORRECT_DATA, msg)
        try:
            total = float(post.get('total', 0.0))
            tax = float(post.get('tax', 0.0))
        except (ValueError, KeyError, TypeError):
            total = tax = 0.0
        if invoice_type == 'out_refund':
            total = abs(total)
            tax = abs(tax)

        msg = 'Invoice total amounts do not match (%s != %s). Contact administrator.' % (
            total, invoice_id.amount_total)
        total_diff = total - invoice_id.amount_total if total else 0.0
        # If total amount difference is bigger than allowed or there are no tax lines to adjust
        if total and (tools.float_compare(abs(total_diff), api_rounding_error, precision_digits=2) > 0 or
                      not invoice_id.tax_line_ids):
            _logger.info('ROBO API: ' + msg)
            return f_resp(at.API_INCORRECT_DATA, msg)
        elif total_diff:
            # Adjust tax to match the total
            invoice_id.write({
                'force_taxes': True
            })
            invoice_id.tax_line_ids[0].amount += total_diff

        # Adjust lines if WooCommerce invoice amount does not match with a calculated total amount
        woocommerce_control_total = tools.float_round(woocommerce_control_total, precision_digits=2)
        total_diff = woocommerce_control_total - invoice_id.amount_total if \
            not tools.float_is_zero(woocommerce_control_total, precision_digits=2) else 0.0
        if not tools.float_is_zero(total_diff, precision_digits=2) and \
                tools.float_compare(abs(total_diff), 0.01, precision_digits=2) <= 0:
            # If there are non-zero tax lines, force taxes
            if invoice_id.tax_line_ids and not tools.float_is_zero(sum(x.amount for x in invoice_id.tax_line_ids),
                                                                   precision_digits=2):
                invoice_id.write({
                    'force_taxes': True
                })
                invoice_id.tax_line_ids[0].amount += total_diff
            # If there are no tax lines, adjust subtotal of a line that is not a discount or a coupon -
            # those lines have a subtotal of 0.0
            else:
                ch_invoice_lines = invoice_id.invoice_line_ids.filtered(lambda x:
                                                                        not tools.float_is_zero(x.price_subtotal,
                                                                                                precision_digits=2))
                ch_invoice_line = ch_invoice_lines[-1] if ch_invoice_lines else False
                if ch_invoice_line:
                    unit = (ch_invoice_line.price_unit * ch_invoice_line.quantity + total_diff) / \
                           ch_invoice_line.quantity  # P3:DivOK
                    ch_invoice_line.price_unit = unit

        if vat_payer and tax and tools.float_compare(tax, invoice_id.amount_tax, precision_digits=2) != 0:
            msg = 'Invoice tax amounts do not match (%s != %s). Contact administrator.' % (
                post.get('tax', 0.0), invoice_id.amount_tax)
            _logger.info('ROBO API: ' + msg)
            return f_resp(at.API_INCORRECT_DATA, msg)
        if not proforma and not draft and not cancelled:
            if not supplier_invoice:
                invoice_id.write({
                    'move_name': post['number'],
                })
                try:
                    invoice_id.with_context(skip_attachments=True).action_invoice_open()
                except exceptions.UserError as e:
                    return f_resp(at.API_INCORRECT_DATA, e.name)
                invoice_id.write({
                    'number': post['number'],
                    'move_name': post['number'],
                    'reference': post['number'],
                })
            else:
                invoice_id.write({
                    'reference': post.get('reference', False) or post['number'],
                })
                try:
                    invoice_id.with_context(skip_attachments=True).action_invoice_open()
                except exceptions.UserError as e:
                    return f_resp(at.API_INCORRECT_DATA, e.name)
            if extended_stock and any(
                    t == 'product' for t in invoice_id.mapped('invoice_line_ids.product_id.product_tmpl_id.type')):
                if 'location' in post:
                    location_code = post['location']
                    warehouse = stock_warehouse_obj.search([('code', '=', location_code)])
                    location = warehouse.lot_stock_id
                    if not warehouse or not location:
                        msg = 'Location %s not found' % location_code
                        _logger.info('ROBO API: ' + msg)
                        return f_resp(at.API_NOT_FOUND, msg)
                elif company.default_api_invoice_picking_stock_warehouse:
                    location = company.default_api_invoice_picking_stock_warehouse.lot_stock_id
                elif stock_warehouse_obj.search([('code', '=', 'WH')], limit=1):
                    location = stock_warehouse_obj.search([('code', '=', 'WH')], limit=1).lot_stock_id
                elif stock_location_obj.search_count([('usage', '=', 'internal')]) == 1:
                    location = stock_location_obj.search([('usage', '=', 'internal')], limit=1)
                else:
                    location = False
                if not location:
                    msg = 'Could not determine location for picking creation'
                    _logger.info('ROBO API: ' + msg)
                    return f_resp(at.API_NOT_FOUND, msg)
                wiz = self.env['invoice.delivery.wizard'].with_context({'invoice_id': invoice_id.id}).create({
                    'location_id': location.id,
                })
                wiz.create_delivery()
                if invoice_id.picking_id:
                    invoice_id.picking_id.action_assign()
                    if invoice_id.picking_id.shipping_type == 'return':
                        invoice_id.picking_id.force_assign()
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()
        elif proforma:
            invoice_id.action_invoice_proforma2()
            invoice_id.write({
                'number': post.get('number'),
            })
        if cancelled:
            invoice_id.write({
                'reference': post.get('reference'),
                'move_name': post.get('reference'),
            })
            invoice_id.action_invoice_cancel()
        if not proforma and 'payments' in post and not supplier_invoice:
            invoice_id.write({
                'reference': post['number'],
                'number': post['number'],
            })
            # Process payments
            payment_response = self._process_invoice_payments(invoice_id, post['payments'])
            if payment_response.get('code', at.API_SUCCESS) != at.API_SUCCESS:
                return payment_response

        if not tools.float_is_zero(
                invoice_id.residual_company_signed, precision_digits=2) and post.get('use_credit'):
            self.reconcile_with_earliest_entries(invoice=invoice_id)
        return f_resp(at.API_SUCCESS)

    @api.model
    def api_update_invoice(self, post):
        """
        Update //
        API endpoint that is used to update account.invoice record
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """

        company = self.env.user.sudo().company_id
        api_force_global_tax = company.api_force_tax_id if company.api_force_tax_selection == 'global' else False
        api_ft_condition = company.api_force_tax_condition
        api_woocommerce = company.api_woocommerce_integration
        api_rounding_error = company.api_max_rounding_error_allowed if company.api_allow_rounding_error else 0.0

        currency_obj = self.env['res.currency'].sudo()
        ForceTaxPosition = self.env['robo.api.force.tax.position']
        AccountAccount = self.env['account.account']

        invoice_vals = {}
        reference = (post.get('reference', str())).strip()
        if reference:
            if ' ' in reference:
                return f_resp(at.API_INCORRECT_DATA, 'Supplier invoice number cannot contain spaces')
            invoice_vals['reference'] = reference
        date_invoice = post.get('date_invoice')
        if date_invoice:
            error_str = check_date_format(date_invoice, 'date_invoice')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            invoice_vals['date_invoice'] = invoice_vals['operacijos_data'] = date_invoice
        registration_date = post.get('registration_date')
        if registration_date:
            error_str = check_date_format(registration_date, 'registration_date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            invoice_vals['registration_date'] = registration_date
        due_date = post.get('due_date')
        if due_date:
            error_str = check_date_format(due_date, 'due_date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            invoice_vals.update({
                'date_due': due_date,
                'payment_term_id': False,
            })
        robo_stock_installed = bool(self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])]))
        warehouse_cost = post.get('warehouse_cost')
        if robo_stock_installed and warehouse_cost:
            invoice_vals.update({'warehouse_cost': warehouse_cost})
        if 'comment' in post:
            invoice_vals['comment'] = (post.get('comment') or '').strip()
        currency_id = False
        if 'currency' in post:
            currency_id = currency_obj.search([('name', '=', post['currency'])], limit=1)
        if currency_id:
            invoice_vals['currency_id'] = currency_id.id
        invoice_id, error_str = self.update_domain_search_overridable(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        if invoice_id.state == 'paid':
            return f_resp(at.API_NOT_FOUND, 'Cannot update invoice that is paid')
        is_proforma = True if invoice_id.state in ['proforma', 'proforma2'] else False
        proforma = post.get('proforma', is_proforma)
        draft = post.get('draft', False)
        cancelled = post.get('cancelled', False)

        if (currency_id or invoice_id.currency_id) != company.currency_id and not (draft or proforma or cancelled):
            if datetime.strptime(invoice_vals.get('date_invoice', invoice_id.date_invoice),
                                 tools.DEFAULT_SERVER_DATE_FORMAT
                                 ).date() > datetime.utcnow().date():
                return f_resp(at.API_INCORRECT_DATA,
                              'Invoice not in company currency cannot be validated at future dates')
        partner = False
        if 'partner' in post:
            partner, error_str = self.find_or_create_partner(post['partner'])
            if error_str:
                return f_resp(at.API_INTERNAL_SERVER_ERROR, error_str)
        if partner and partner.id != invoice_id.partner_id.id:
            invoice_vals['partner_id'] = partner.id
            invoice_vals['intrastat_country_id'] = partner.country_id.id
        if 'language' in post:
            language = post.get('language', 'LT')
            if language not in LANGUAGE_MAPPING:
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice language')
            invoice_vals['partner_lang'] = LANGUAGE_MAPPING[language]
        total_tax = 0.0
        total_wo_amount = 0.0
        all_prices_wo_vat = True
        try:
            control_subtotal = float(post.get('subtotal', 0.0))
        except (ValueError, KeyError, TypeError):
            control_subtotal = 0.0
        supplier_invoice = True if invoice_id.type in ['in_invoice', 'in_refund'] else False
        force_type = post.get('force_type', False)
        negative = False
        positive = False
        abs_prices = False
        inv_types = ['in_invoice', 'in_refund', 'out_invoice', 'out_refund']
        if post.get('invoice_lines'):
            for line in post['invoice_lines']:
                try:
                    price = float(line.get('price', 0.0))
                except (ValueError, KeyError, TypeError):
                    price = 0.0
                if not price:
                    try:
                        price = float(line.get('price_with_vat', 0.0))
                    except (ValueError, KeyError, TypeError):
                        return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')
                if price < 0.0 and not negative:
                    negative = True
                if price > 0.0 and not positive:
                    positive = True

        if force_type and force_type in inv_types:
            if force_type in ['out_refund', 'in_refund'] and negative and positive:
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')
            if force_type in ['out_refund', 'in_refund'] and negative and not positive:
                abs_prices = True
            invoice_type = force_type
            supplier_invoice = force_type in ['in_invoice', 'in_refund']
        else:
            if control_subtotal < 0.0:
                invoice_type = 'in_refund' if supplier_invoice else 'out_refund'
                control_subtotal = abs(control_subtotal)
                abs_prices = True
            elif control_subtotal > 0.0:
                invoice_type = 'in_invoice' if supplier_invoice else 'out_invoice'
            else:
                if negative and not positive:
                    invoice_type = 'in_refund' if supplier_invoice else 'out_refund'
                    abs_prices = True
                else:
                    invoice_type = 'in_invoice' if supplier_invoice else 'out_invoice'
        vat_payer_date = invoice_vals.get('date_invoice', invoice_id.get_vat_payer_date())
        vat_payer = self.env.user.company_id.with_context(date=vat_payer_date).vat_payer
        if 'invoice_lines' in post:
            invoice_lines = [(5,)]
            invoice_vals['invoice_line_ids'] = invoice_lines
            for line in post['invoice_lines']:
                product_id, error_str = self.find_or_create_product(line)
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)

                product = (line.get('product') or '').strip()
                description = (line.get('description') or '').strip()
                description = description if len(description) <= 200 else ''

                if 'qty' not in line or not isinstance(line['qty'], tuple([int, float, long])):
                    if 'qty' in line:
                        try:
                            qty_converted = float(line['qty'])
                            line['qty'] = qty_converted
                        except ValueError:
                            return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty field.')
                    else:
                        return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty field.')

                no_price = no_price_vat = False
                # Try to get price with VAT
                try:
                    price_converted = float(line['price_with_vat'])
                    line['price_with_vat'] = price_converted
                except (ValueError, KeyError):
                    no_price_vat = True

                # Try to get price
                try:
                    price_converted = float(line['price'])
                    line['price'] = price_converted
                except (ValueError, KeyError):
                    no_price = True

                # If price and price with vat does not exist, raise an error
                if no_price and no_price_vat:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')

                # Try to convert vat rate
                try:
                    vat_converted = float(line['vat'])
                    line['vat'] = vat_converted
                except (ValueError, KeyError):
                    pass

                # Try to get discount
                try:
                    discount = abs(float(line['discount']))
                    # Check for percentage
                    if discount < 0 or discount > 100:
                        return f_resp(at.API_INCORRECT_DATA,
                                      'Incorrect invoice line discount field, value must be between 0 and 100.')
                    line['discount'] = discount
                except (ValueError, KeyError, TypeError):
                    line['discount'] = 0.0

                if no_price and no_price_vat:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line price field.')

                tax_ids = []
                # Check whether forced API taxes would be applied
                apply_api_ft = not supplier_invoice and api_woocommerce \
                               and api_ft_condition in ['force_if_none', 'force_on_gaps'] and vat_payer
                # If call is from WooCommerce, check tax forcing conditions:
                if apply_api_ft:
                    if api_force_global_tax:
                        # Shipping always has vat/vat_code specified in plugin so
                        # an explicit check is needed when applying tax
                        is_shipping = line.get('product', str()) == 'Shipping'
                        # If forced taxes condition is 'force_if_none' and
                        # forced taxes would be applied -- no vat can be passed
                        if line.get('vat') and api_ft_condition == 'force_if_none' and not is_shipping:
                            return f_resp(at.API_NOT_FOUND, 'VAT amount was specified for order from WooCommerce.')

                        # Otherwise, apply taxes if no vat rate/zero vat rate or no vat_code is passed,
                        # or it is a shipping line
                        elif not line.get('vat') or not line.get('vat_code') or is_shipping:
                            line.pop('vat', False)
                            tax_ids = api_force_global_tax.ids
                            line['vat_code'] = api_force_global_tax.code
                            if api_force_global_tax.price_include:
                                if 'price' in line:
                                    # Act like price with VAT was specified
                                    line['price_with_vat'] = line.pop('price')
                                    no_price_vat = False
                    else:
                        invoice_date = invoice_vals.get('date_invoice', invoice_id.date_invoice)
                        api_force_tax = ForceTaxPosition.get_tax_of_position_applied(partner.id, invoice_date,
                                                                                     product_id.acc_product_type)
                        if api_force_tax:
                            tax_ids = api_force_tax.ids
                            line['vat_code'] = api_force_tax.code
                            if api_force_tax.price_include:
                                if 'price' in line:
                                    # Act like price with VAT was specified
                                    try:
                                        line['price_with_vat'] = line.pop('price') + line.pop('vat', 0.0) / \
                                                                 abs(line['qty'])  # P3:DivOK
                                    except ZeroDivisionError:
                                        return f_resp(at.API_INCORRECT_DATA, 'Incorrect invoice line qty.')
                                    no_price_vat = False

                account_code = (line.get('account_code') or '').strip()
                if account_code:
                    product_account = AccountAccount.search([('code', '=', account_code)], limit=1)
                    if not product_account:
                        return f_resp(at.API_NOT_FOUND, 'Account of code %s not found for invoice line.' % account_code)
                elif not supplier_invoice:
                    product_account = product_id.get_product_income_account(return_default=True)
                else:
                    product_account = product_id.get_product_expense_account(return_default=True)

                invoice_vat_code = line['vat_code'] if 'vat_code' in line else False
                if not invoice_vat_code and vat_payer and not tools.float_compare(
                        line.get('price', 0), 0.0, precision_digits=2):
                    line['vat_code'] = invoice_vat_code = 'PVM1'

                if not invoice_vat_code and vat_payer:
                    return f_resp(at.API_INCORRECT_DATA, 'Missing tax code')

                # If client is not VAT payer, and price with VAT is not provided, set price to be price with VAT
                if not vat_payer and no_price_vat:
                    # Set price with VAT (already checked for existence and type before)
                    line['price_with_vat'] = line.get('price')

                if 'price_with_vat' in line:
                    prices_with_vat = True
                    all_prices_wo_vat = False
                else:
                    prices_with_vat = False

                if vat_payer and not tax_ids:
                    tax_ids = self.find_corresponding_taxes(line, supplier_invoice)
                    if not tax_ids:
                        return f_resp(at.API_NOT_FOUND, 'Could not find tax code %s' % invoice_vat_code)

                if prices_with_vat:
                    if abs_prices:
                        line['price_with_vat'] = abs(line.get('price_with_vat', 0.0))
                    line['price'] = line['price_with_vat']
                if abs_prices:
                    line['price'] = abs(line.get('price', 0.0))
                    line['qty'] = abs(line.get('qty', 0.0))
                total_wo_amount += line['price'] * line['qty']
                line_vals = {
                    'product_id': product_id.id,
                    'name': description or product_id.partner_ref or product,
                    'quantity': line['qty'],
                    'price_unit': line['price'],
                    'uom_id': self.env.ref('product.product_uom_unit').id,
                    'discount': line['discount'],
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, tax_ids)]
                }

                deferred_data, error_str = self.get_deferred_data(line, invoice_type, product_account)
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)
                if deferred_data:
                    line_vals.update(deferred_data)

                analytic_account, error_str = self.find_or_create_analytic_account(line)
                if error_str:
                    return f_resp(at.API_NOT_FOUND, error_str)
                if analytic_account:
                    invoice_vals['account_analytic_id'] = analytic_account.id
                invoice_lines.append((0, 0, line_vals))
                if 'vat' in line and line['vat']:
                    total_tax += line['vat']
            invoice_vals['type'] = invoice_type
        if invoice_vals:
            invoice_vals['skip_isaf'] = post.get('skip_isaf', False)
            is_validated = invoice_id.accountant_validated
            if is_validated:
                invoice_id.accountant_validated = False
            invoice_id.action_invoice_cancel()
            invoice_id.action_invoice_draft()
            invoice_id.write(invoice_vals)
            if 'invoice_line_ids' in invoice_vals:
                invoice_id.recalculate_taxes()
            invoice_id.with_context(skip_vat_constrains=True).partner_data_force()
            if total_tax:
                tax_diff = abs(abs(invoice_id.amount_tax) - total_tax)
                if tools.float_compare(tax_diff, 0.05, precision_digits=2) > 0:
                    return f_resp(
                        at.API_INCORRECT_DATA,
                        'Incorrect taxes. %s != %s' % (str(abs(invoice_id.amount_tax)), str(total_tax)))
                elif tools.float_compare(tax_diff, 0.0, precision_digits=2) > 0:
                    invoice_id.write({
                        'force_taxes': True
                    })
                    amount_diff = abs(invoice_id.amount_tax) - total_tax
                    if invoice_id.tax_line_ids:
                        invoice_id.tax_line_ids[0].amount -= amount_diff
            # check total amounts
            if not control_subtotal:
                control_subtotal = total_wo_amount
            if all_prices_wo_vat:
                invoice_amount_total = sum(invoice_id.mapped('invoice_line_ids.price_subtotal'))
                if tools.float_compare(control_subtotal, invoice_amount_total,
                                       precision_digits=2) != 0:
                    diff = control_subtotal - invoice_amount_total
                    if tools.float_compare(abs(diff), 0.05, precision_digits=2) <= 0:
                        ch_invoice_line_id = invoice_id.invoice_line_ids[-1]
                        ch_invoice_line_id.price_unit = \
                            (ch_invoice_line_id.price_unit * ch_invoice_line_id.quantity + diff) \
                            / ch_invoice_line_id.quantity  # P3:DivOK
                    else:
                        msg = 'Invoice subtotal amounts do not match (%s != %s). Contact administrator.' % (
                            control_subtotal, invoice_amount_total)
                        _logger.info('ROBO API: ' + msg)
                        return f_resp(at.API_INCORRECT_DATA, msg)
            try:
                total = float(post.get('total', 0.0))
            except (ValueError, KeyError, TypeError):
                total = 0.0
            msg = 'Invoice total amounts do not match (%s != %s). Contact administrator.' % (
                total, invoice_id.amount_total)
            total_diff = total - invoice_id.amount_total if total else 0.0
            # If total amount difference is bigger than allowed or there are no tax lines to adjust
            if total and (tools.float_compare(abs(total_diff), api_rounding_error,
                                              precision_digits=2) > 0 or not invoice_id.tax_line_ids):
                _logger.info('ROBO API: ' + msg)
                return f_resp(at.API_INCORRECT_DATA, msg)
            elif total_diff:
                # Adjust tax to match the total
                invoice_id.write({
                    'force_taxes': True
                })
                invoice_id.tax_line_ids[0].amount += total_diff

            try:
                tax = float(post.get('tax', 0.0))
            except (ValueError, KeyError, TypeError):
                tax = 0.0
            if vat_payer and tax and tools.float_compare(tax, invoice_id.amount_tax, precision_digits=2) != 0:
                msg = 'Invoice tax amounts do not match (%s != %s). Contact administrator.' % (
                    post.get('tax', 0.0), invoice_id.amount_tax)
                _logger.info('ROBO API: ' + msg)
                return f_resp(at.API_INCORRECT_DATA, msg)
            if proforma and not draft:
                invoice_id.action_invoice_proforma2()
            elif not draft and not cancelled:
                try:
                    invoice_id.with_context(skip_attachments=True).action_invoice_open()
                except exceptions.UserError as e:
                    return f_resp(at.API_INCORRECT_DATA, e.name)
            elif not draft and cancelled:
                invoice_id.action_invoice_cancel()
            if is_validated:
                invoice_id.accountant_validated = True
        if not proforma and 'add_payments' in post and invoice_type in ['out_refund', 'out_invoice']:
            # Process payments
            payment_response = self._process_invoice_payments(invoice_id, post['add_payments'])
            if payment_response.get('code', at.API_SUCCESS) != at.API_SUCCESS:
                return payment_response
        if not tools.float_is_zero(
                invoice_id.residual_company_signed, precision_digits=2) and post.get('use_credit'):
            self.reconcile_with_earliest_entries(invoice=invoice_id)
        return f_resp(at.API_SUCCESS)

    @api.model
    def api_unlink_invoice(self, post):
        """
        Delete //
        API endpoint that is used to unlink account.invoice record
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        invoice, error_str = self.cancel_unlink_domain_search_overridable(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        if invoice:
            if len(invoice) > 1:
                error_str = 'Invoice was not deleted due to ambiguity, match count %s | invoice %s ' % \
                            (len(invoice), post.get('reference', post.get('move_name', '')))
                return f_resp(at.API_INCORRECT_DATA, error_str)
            else:
                try:
                    # Unlink related account payments (ignore delete_payment option, because related
                    # account payment is artificial and cannot exist without invoice record - SQL constraint)
                    for account_payment in invoice.payment_ids:
                        account_payment.cancel()
                        account_payment.unlink()

                    if at.process_bool_value(post.get('delete_payment', False)):
                        res = invoice.action_invoice_cancel_draft_and_remove_outstanding()

                        payments = res.get('payment_lines').mapped('move_id')
                        payments |= res.get('expense_payment_lines').mapped('move_id')
                        payments |= res.get('gpm_payment_lines').mapped('move_id')

                        # Unlink only those related payment moves which do not contain any reconciled lines
                        for payment in payments.filtered(lambda pmt: all(not x.reconciled for x in pmt.line_ids)):
                            payment.button_cancel()
                            payment.unlink()

                    else:
                        invoice.action_invoice_cancel_draft()
                    invoice.write({'move_name': False, 'number': False})
                    if self.env['ir.module.module'].sudo().search(
                            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])], count=True):
                        if invoice.picking_id and invoice.picking_id.state == 'done':
                            picking_return = self.env['stock.return.picking'].sudo().with_context(
                                active_id=invoice.picking_id.id).create({'mistake_type': 'cancel', 'error': True})
                            picking_return._create_returns()
                        elif invoice.picking_id:
                            invoice.picking_id.unlink()
                    invoice.unlink()
                    return f_resp(at.API_SUCCESS)
                except Exception as e:
                    error_str = 'Unexpected error while deleting invoice | invoice %s' \
                                % (post.get('reference', post.get('move_name', '')))
                    system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
                    _logger.info(system_error)
                    return f_resp(at.API_INTERNAL_SERVER_ERROR, error_str, system_error)
        else:
            error_str = 'Invoice not found | invoice %s' % \
                        post.get('reference', post.get('move_name', post.get('number', '')))
            return f_resp(at.API_NOT_FOUND, error_str)

    @api.model
    def api_cancel_invoice(self, post):
        """
        Cancel //
        API endpoint that is used to cancel account.invoice record
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        invoice, error_str = self.cancel_unlink_domain_search_overridable(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        if invoice:
            if len(invoice) > 1:
                error_str = 'Invoice was not canceled due to ambiguity, match count %s | invoice %s ' % \
                            (len(invoice), post.get('reference', post.get('move_name', '')))
                return f_resp(at.API_INCORRECT_DATA, error_str)
            else:
                try:
                    if invoice.state == 'cancel':
                        return f_resp(at.API_INCORRECT_DATA, 'Invoice is already canceled!')

                    company = self.env.user.sudo().company_id
                    robo_stock_installed = bool(self.env['ir.module.module'].search_count(
                        [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])]))
                    extended_stock = robo_stock_installed and company.politika_sandelio_apskaita == 'extended'

                    if extended_stock and any(t == 'product' for t in
                                              invoice.mapped('invoice_line_ids.product_id.product_tmpl_id.type')):
                        if not invoice.picking_id:
                            return f_resp(at.API_FORBIDDEN, 'Invoice does not have a related picking '
                                                            'and should be cancelled manually!')

                        if invoice.picking_id.state == 'done':
                            picking_return = self.env['stock.return.picking'].sudo().with_context(
                                active_id=invoice.picking_id.id).create({'mistake_type': 'cancel', 'error': True})
                            picking_return._create_returns()
                        else:
                            invoice.picking_id.unlink()

                    if at.process_bool_value(post.get('delete_payment', False)):
                        res = invoice.remove_outstanding_payments()

                        payments = res.get('payment_lines').mapped('move_id')
                        payments |= res.get('expense_payment_lines').mapped('move_id')
                        payments |= res.get('gpm_payment_lines').mapped('move_id')

                        # Unlink only those related payment moves which do not contain any reconciled lines
                        for payment in payments.filtered(lambda pmt: all(not x.reconciled for x in pmt.line_ids)):
                            payment.button_cancel()
                            payment.unlink()

                    invoice.action_invoice_cancel()

                    return f_resp(at.API_SUCCESS)
                except Exception as e:
                    error_str = 'Unexpected error while cancelling invoice | invoice %s' \
                                % post.get('reference', post.get('move_name', post.get('number', '')))
                    system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
                    _logger.info(system_error)
                    return f_resp(at.API_INTERNAL_SERVER_ERROR, error_str, system_error)
        else:
            error_str = 'Invoice not found | %s' % post.get('reference', post.get('number', ''))
            return f_resp(at.API_NOT_FOUND, error_str)

    @api.model
    def api_get_invoice(self, post):
        """
        Get //
        API endpoint that is used to return account.invoice data
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        pdf = post.get('pdf', False)
        invoice, error_str = self.find_invoice(post)
        if error_str:
            return f_resp(at.API_NOT_FOUND, error_str)

        if invoice:
            invoice_data = self.get_invoice_data(invoice, pdf)
            return f_resp(at.API_SUCCESS, 'Invoice was found in the system.', data=invoice_data)

        return f_resp(at.API_NOT_FOUND, 'Invoice was not found in the system')

    @api.model
    def api_get_invoice_list(self, post):
        """
        Get //
        API endpoint that is used to return account.invoice records data
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        date_from = post.get('date_from')
        date_to = post.get('date_to')
        data_type = post.get('data_type', 'create')
        invoice_date_from = post.get('invoice_date_from')
        invoice_date_to = post.get('invoice_date_to')
        domain = []
        if (not date_from or not date_to) and (not invoice_date_from or not invoice_date_to):
            return f_resp(at.API_INCORRECT_DATA, 'Missing information about dates.')
        if date_from and date_to:
            error_str = check_datetime_format(date_from, 'date_from')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            error_str = check_datetime_format(date_to, 'date_to')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)

            if data_type == 'create':
                domain = [('create_date', '<=', date_to), ('create_date', '>=', date_from)]
            elif data_type == 'modify':
                domain = [('write_date', '<=', date_to), ('write_date', '>=', date_from)]
            else:
                return f_resp(at.API_NOT_FOUND, 'Data type not found, it should be "create" or "modify".')

        elif invoice_date_from and invoice_date_to:
            error_str = check_date_format(invoice_date_from, 'invoice_date_from')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            error_str = check_date_format(invoice_date_to, 'invoice_date_to')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            domain = [('date_invoice', '<=', invoice_date_to), ('date_invoice', '>=', invoice_date_from)]

        invoice_data = []
        invoices = self.env['account.invoice'].sudo().search(domain)
        for invoice in invoices:
            invoice_data.append(self.get_invoice_data(invoice, False))

        if not invoice_data:
            return f_resp(at.API_NOT_FOUND, 'No invoices were found!')

        return f_resp(at.API_SUCCESS, data=invoice_data)

    @api.model
    def api_add_invoice_document(self, post):
        """
        Create //
        API endpoint that is used to create a document and attach it to invoice
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        attach_document = self._context.get('attach_document')
        invoice = self.env['account.invoice']
        if attach_document:
            invoice, error_str = self.find_invoice(post)
        else:
            error_str = self.check_invoice_identifying_fields(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        invoice_id = invoice.id if invoice else False
        attachment, error_str = self.create_attachment(post, invoice_id)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        return f_resp(at.API_SUCCESS, data={'attachment_id': attachment.id})

    @api.model
    def api_create_partner_payments(self, post):
        """
        Create //
        API endpoint that is used to create account.move records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        company = self.env.user.sudo().company_id

        ResCurrency = self.env['res.currency']
        AccountJournal = self.env['account.journal']
        AccountAccount = self.env['account.account']
        AccountMove = self.env['account.move']

        partner, error_str = self.find_or_create_partner(post)
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        default_account = AccountAccount.search([('code', '=', '2410')], limit=1)

        payments = post['payments'] if isinstance(post['payments'], list) else []
        for payment in payments:
            payer = (payment.get('payer') or '').strip()
            if not payer:
                return f_resp(at.API_INCORRECT_DATA, 'Missing payer property.')

            payer_partner = None
            if company.api_create_payer_partners:
                payer_partner, error_str = self.find_or_create_partner({'name': payer})
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)

            ref = (payment.get('ref') or '').strip()
            if not ref:
                return f_resp(at.API_INCORRECT_DATA, 'Missing payment reference.')
            ref = u'Apmokėjo ' + payer + u' - ' + unicode(payment['ref'])

            existing_payment = AccountMove.search([('ref', '=', ref)])
            if existing_payment:
                continue

            payment_journal_code = (payment.get('journal_code') or 'CARD').upper()
            payment_journal_name = payment.get('journal_name') or 'Payments'

            if len(payment_journal_code) > 5:
                return f_resp(at.API_INCORRECT_DATA, 'Failed preparing payment. Wrong journal code: "%s". '
                                                     'Code length cannot exceed 5 characters' % payment_journal_code)
            payment_journal = AccountJournal.search([('code', '=', payment_journal_code)], limit=1)
            if not payment_journal:
                if not payment_journal_name:
                    return f_resp(at.API_INCORRECT_DATA, 'Failed preparing payment. Journal with code "%s" not found. '
                                                         'Please provide a journal_name' % payment_journal_code)
                payment_journal = AccountJournal.search([('name', '=', payment_journal_name)], limit=1)
            if not payment_journal:
                payment_journal = AccountJournal.create({
                    'name': payment_journal_name,
                    'code': payment_journal_code,
                    'type': 'bank',
                })
            if not payment_journal:
                return f_resp(at.API_NOT_FOUND,
                              'Failed preparing payment because payment journal was not found.')

            if 'amount' not in payment or not isinstance(payment['amount'], tuple([int, float, long])):
                return f_resp(at.API_INCORRECT_DATA, 'Missing or incorrect payment amount field.')
            pos_amount = True if tools.float_compare(payment['amount'], 0.0, precision_digits=2) > 0 else False
            amount = abs(payment['amount'])

            date = (payment.get('date') or '').strip()
            if not date:
                return f_resp(at.API_INCORRECT_DATA, 'Missing payment date.')
            error_str = check_date_format(date, 'date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)

            payment_currency = False
            payment_amount_currency = 0.0
            currency = (payment.get('currency') or '').strip()
            if currency != company.currency_id.name:
                payment_currency = ResCurrency.search([('name', '=', currency)], limit=1)
                if not payment_currency:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect payment currency.')
                payment_amount_currency = amount
                amount = payment_currency.with_context(date=date).compute(amount, company.currency_id)

            name = (payment.get('name') or '').strip()
            name = unicode(name) if name else u'Mokėjimas ' + payer

            lines = []
            line1_vals = {
                'name': name,
                'account_id': default_account.id,
                'date': date,
            }

            if payment_currency:
                line1_vals['currency_id'] = payment_currency.id
                sign = -1.0 if pos_amount else 1.0
                line1_vals['amount_currency'] = payment_amount_currency * sign

            if pos_amount:
                line1_vals['credit'] = amount
                line1_vals['debit'] = 0.0
            else:
                line1_vals['debit'] = amount
                line1_vals['credit'] = 0.0
            line2_vals = {
                'name': name,
                'date': date,
                'partner_id': payer_partner.id if payer_partner else None
            }
            if payment_currency:
                line2_vals['currency_id'] = payment_currency.id
                sign = 1.0 if pos_amount else -1.0
                line2_vals['amount_currency'] = payment_amount_currency * sign

            if pos_amount:
                line2_vals['debit'] = amount
                line2_vals['credit'] = 0.0
                line2_vals['account_id'] = payment_journal.default_debit_account_id.id
            else:
                line2_vals['credit'] = amount
                line2_vals['debit'] = 0.0
                line2_vals['account_id'] = payment_journal.default_credit_account_id.id

            lines.append((0, 0, line1_vals))
            lines.append((0, 0, line2_vals))
            move_vals = {
                'ref': ref,
                'line_ids': lines,
                'journal_id': payment_journal.id,
                'date': date,
                'partner_id': partner.id,
            }
            move = AccountMove.create(move_vals)
            move.post()

        return f_resp(at.API_SUCCESS)

    @api.model
    def create_partner_bank(self, partner, bank_information):
        Bank = self.env['res.bank']
        PartnerBank = self.env['res.partner.bank']
        error_str = str()
        if not bank_information:
            return False, error_str

        # Check account number (IBAN) (Always required)
        acc_number = bank_information.get('acc_number')
        if not acc_number:
            error_str = 'Missing account number'
            return False, error_str

        # Look up partner bank by IBAN
        partner_bank = PartnerBank.search([('partner_id', '=', partner.id), ('acc_number', '=', acc_number)], limit=1)
        if partner_bank:
            return partner_bank, error_str

        # Get BIC from IBAN or from the bank information provided
        bic_by_open_iban = self._get_bic_from_iban(acc_number)
        bic_from_data = bank_information.get('bic')
        bic = bic_by_open_iban or bic_from_data
        # Get the bank code from the bank information provided
        bank_code = bank_information.get('bank_code')
        # If neither is provided - it's impossible to look up or create a bank record
        if not bic and not bank_code:
            error_str = 'Missing BIC or Bank code'
            return False, error_str

        # Look for res.bank by the BIC and then (if not found) by bank code.
        bank = None
        if bic_from_data:
            bank = Bank.search([('bic', '=', bic_from_data)], limit=1)
        if not bank and bic_by_open_iban:
            bank = Bank.search([('bic', '=', bic_by_open_iban)], limit=1)
        if not bank and bank_code:
            bank = Bank.search([('kodas', '=', bank_code)], limit=1)
            if not bank:
                bank = Bank.search([('kodas', '=like', bank_code[:3] + '%')], limit=1)

        # If the bank doesn't exist in the system - create it
        if not bank:
            # Check the required data is in the request for the creation of the res.bank record
            if not bic:
                error_str = 'Missing BIC'
                return False, error_str
            if not bank_code:
                error_str = 'Missing bank code'
                return False, error_str
            name = bank_information.get('bank_name')
            if not name:
                error_str = 'Missing bank name'
                return False, error_str

            bank = Bank.create({'kodas': bank_code, 'bic': bic, 'name': name})

        # Create the partner bank record and return it
        partner_bank = PartnerBank.create({'acc_number': acc_number, 'bank_id': bank.id, 'partner_id': partner.id})
        return partner_bank, error_str

    @api.model
    def _get_bic_from_iban(self, iban):
        """ Calls OpenIBAN to get the BIC from the provided IBAN """
        bic = None
        try:
            _logger.debug('Retrieving banking details from IBAN (Calling OpenIBAN)')
            openiban = requests.get('https://openiban.com/validate/%s?getBIC=true' % iban, timeout=30)
            request_result = json.loads(openiban.content)
            bic = request_result['bankData']['bic']
        except:
            _logger.debug('Could not retrieve BIC from IBAN (%s)', str(iban))

        return bic

    @api.model
    def api_create_accounting_entries(self, post):
        """
        Create //
        API endpoint that is used to create account.move records
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code
        """
        company = self.env.user.sudo().company_id
        api_allow_empty_partner_code = company.api_allow_empty_partner_code
        AccountAccount = self.env['account.account']
        ResPartner = self.env['res.partner']
        AccountJournal = self.env['account.journal']
        AccountMove = self.env['account.move']

        grouped_lines = {}
        if not post.get('entries'):
            return f_resp(at.API_INCORRECT_DATA, 'Missing entries')
        entries = post['entries'] if isinstance(post['entries'], list) else [post['entries']]
        for entry in entries:
            partner_name = (entry.get('partner_name') or '').strip()
            if not partner_name:
                return f_resp(at.API_INCORRECT_DATA, 'Missing partner name.')

            is_company = entry.get('is_company', False)
            partner_code = (entry.get('partner_code') or '').strip()
            if is_company and not partner_code and not api_allow_empty_partner_code:
                return f_resp(at.API_INCORRECT_DATA, 'Missing partner code.')

            partner = False
            if partner_code:
                partner = ResPartner.search([('kodas', '=', partner_code)], limit=1)
            if not partner and partner_name:
                partner = ResPartner.search([('name', '=', partner_name)], limit=1)
            if not partner:
                try:
                    partner = ResPartner.create({
                        'name': partner_name,
                        'kodas': partner_code,
                        'is_company': is_company,
                    })
                except Exception as e:
                    _logger.info('ROBO API EXCEPTION: %s' % e)
                    return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Could not create partner.')

            journal_code = (entry.get('journal_code') or 'KITA').upper()
            journal_name = entry.get('journal_name') or 'Kitos operacijos'

            if len(journal_code) > 5:
                return f_resp(at.API_INCORRECT_DATA, 'Failed preparing entry. Wrong journal code: "%s". '
                                                     'Code length cannot exceed 5 characters' % journal_code)
            journal = AccountJournal.search([('code', '=', journal_code)], limit=1)
            if not journal:
                if not journal_name:
                    return f_resp(at.API_NOT_FOUND, 'Failed preparing entry. Journal with code "%s" not found. '
                                                    'Please provide a journal_name' % journal_code)
                journal = AccountJournal.search([('name', '=', journal_name)], limit=1)
            if not journal:
                try:
                    journal = AccountJournal.create({
                        'name': journal_name,
                        'code': journal_code,
                        'type': 'general',
                        'update_posted': True,
                    })
                except Exception as e:
                    system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
                    _logger.info(system_error)
                    return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Failed preparing entry. Cannot create journal.')

            name = (entry.get('entry_name') or '').strip()
            if not name:
                return f_resp(at.API_INCORRECT_DATA, 'Missing entry name.')

            code = (entry.get('account_code') or '').strip()
            if not code:
                return f_resp(at.API_INCORRECT_DATA, 'Missing account code.' % code)

            account = AccountAccount.search([('code', '=', code)], limit=1)
            if not account:
                return f_resp(at.API_NOT_FOUND, 'Failed preparing entry. Account of code %s not found.' % code)

            date = (entry.get('date') or '').strip()
            if not date:
                return f_resp(at.API_INCORRECT_DATA, 'Missing entry date.')
            error_str = check_date_format(date, 'date')
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)

            debit = entry.get('debit', 0.0)
            if not isinstance(debit, tuple([int, float, long])):
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect entry debit value.')

            credit = entry.get('credit', 0.0)
            if not isinstance(credit, tuple([int, float, long])):
                return f_resp(at.API_INCORRECT_DATA, 'Incorrect entry credit value.')

            if tools.float_is_zero(debit, precision_digits=2) and tools.float_is_zero(credit, precision_digits=2):
                return f_resp(at.API_INCORRECT_DATA, 'Missing debit and credit values.')

            line_vals = {
                'name': name,
                'account_id': account.id,
                'debit': debit,
                'credit': credit,
                'journal_id': journal.id,
                'partner_id': partner.id,
                'date': date,
            }

            date_maturity = (entry.get('date_maturity') or '').strip()
            if date_maturity:
                error_str = check_date_format(date_maturity, 'date_maturity')
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)
                line_vals['date_maturity'] = date_maturity

            analytic_account, error_str = self.find_or_create_analytic_account(entry)
            if error_str:
                return f_resp(at.API_INCORRECT_DATA, error_str)
            if analytic_account:
                line_vals['analytic_account_id'] = analytic_account.id

            currency_name = (entry.get('currency') or '').strip()
            if currency_name and currency_name != company.currency_id.name:
                currency = self.env['res.currency'].search([('name', '=', currency_name)], limit=1)
                if not currency:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect entry currency.')

                currency_amount = entry.get('amount_currency', 0.0)
                if not currency_amount or not isinstance(currency_amount, tuple([int, float, long])):
                    return f_resp(at.API_INCORRECT_DATA, 'Missing or incorrect entry currency amount field.')
                sign = 1.0 if tools.float_compare(currency_amount, 0.0, precision_digits=2) > 0 else -1.0
                line_vals['amount_currency'] = currency_amount * sign
                line_vals['currency_id'] = currency.id

            a_code = (entry.get('a_class_code') or '').strip()
            if a_code:
                a_class_code = self.env['a.klase.kodas'].search([('code', '=', a_code)], limit=1)
                if not a_class_code:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect A class code.')
                line_vals['a_klase_kodas_id'] = a_class_code.id

            b_code = (entry.get('b_class_code') or '').strip()
            if b_code:
                b_class_code = self.env['b.klase.kodas'].search([('code', '=', b_code)], limit=1)
                if not b_class_code:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect B class code.')
                line_vals['b_klase_kodas_id'] = b_class_code.id

            group_num = (entry.get('group_num') or '').strip()
            ref = (entry.get('reference') or '').strip()
            grouped_lines.setdefault(group_num, {})
            grouped_lines[group_num].setdefault(journal, {})
            grouped_lines[group_num][journal].setdefault(date, {})
            grouped_lines[group_num][journal][date].setdefault(ref, []).append(line_vals)

        for group_num, lines_by_journal in grouped_lines.items():
            for journal, lines_by_date in lines_by_journal.items():
                for date, lines_by_reference in lines_by_date.items():
                    for reference, lines in lines_by_reference.items():
                        balance = sum(line['debit'] - line['credit'] for line in lines)
                        if not tools.float_is_zero(balance, precision_digits=2):
                            return f_resp(at.API_INCORRECT_DATA, 'Unbalanced entry.')
                        move_vals = {
                            'date': date,
                            'ref': reference,
                            'journal_id': journal.id,
                            'line_ids': [(0, 0, val) for val in lines],
                        }
                        try:
                            move = AccountMove.create(move_vals)
                            move.post()
                        except Exception as e:
                            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
                            _logger.info(system_error)
                            return f_resp(at.API_INTERNAL_SERVER_ERROR, 'Cannot create journal entry.')

        return f_resp(at.API_SUCCESS)

    @api.model
    def api_get_accounting_entries(self, post):
        """
        Get //
        API endpoint that is used to fetch account.move.line records by date
        :param post: Data posted to API endpoint
            Sample post request is defined in controllers
        :return: response text, response code, response data
        """
        date_from = post.get('date_from')
        date_to = post.get('date_to')
        if not date_from or not date_to:
            return f_resp(at.API_INCORRECT_DATA, 'Missing date from or date to.')
        error_str = check_date_format(date_from, 'date_from')
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)
        error_str = check_date_format(date_to, 'date_to')
        if error_str:
            return f_resp(at.API_INCORRECT_DATA, error_str)

        entry_response_limit = self.env['ir.config_parameter'].sudo().get_param('robo_api_gl_entry_response_limit')

        if not isinstance(entry_response_limit, int):
            try:
                entry_response_limit = int(entry_response_limit)
            except (ValueError, TypeError):
                entry_response_limit = 1000

        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if entry_response_limit:
            moves = self.env['account.move'].sudo().search(domain, limit=entry_response_limit)
        else:
            moves = self.env['account.move'].sudo().search(domain)
        move_data = []
        for move in moves:
            move_data.append({
                'name': move.name,
                'reference': move.ref,
                'date': move.date,
                'journal_code': move.journal_id.code,
                'journal_name': move.journal_id.name,
                'state': move.state,
                'lines': [{
                    'name': line.name,
                    'account_code': line.account_id.code,
                    'partner_code': line.partner_id.kodas or str(),
                    'partner_name': line.partner_id.name or str(),
                    'analytic_code': line.analytic_account_id.code or str(),
                    'debit': line.debit,
                    'credit': line.credit,
                    'date_maturity': line.date_maturity,
                    'currency': line.currency_id.name or str(),
                    'amount_currency': line.amount_currency,
                    'a_class_code': line.a_klase_kodas_id.code or str(),
                    'b_class_code': line.b_klase_kodas_id.code or str(),
                } for line in move.line_ids]
            })

        message = str()
        if not move_data:
            message = 'No accounting entries were found!'
            status_code = at.API_NOT_FOUND
        else:
            status_code = at.API_SUCCESS
        return f_resp(status_code, message, data=move_data)

    # Utility methods -------------------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------------------------------

    @api.model
    def add_extra_vals_overridable(self, invoice_vals, post):
        """
        Used to add extra values to invoice_vals
        :param invoice_vals: account.invoice values
        :param post: API post
        :return: updated invoice values
        """
        # Use post variable, for now it's unused
        _ = post

        vals = {}
        invoice_vals.update(vals)
        return invoice_vals

    @api.model
    def cancel_unlink_domain_search_overridable(self, post):
        """
        Overridable method used to extend the domain
        for account.invoice cancel or unlink operation
        :param post: API post
        :return: account.invoice, error_str
        """
        error_str = str()
        move_name = post.get('move_name', post.get('number'))
        reference = post.get('reference')
        partner_ref = post.get('partner_code', post.get('partner_reference'))

        if not move_name and not (reference and partner_ref):
            error_str = 'Missing data | Please provide invoice move_name or partner_code and reference'
            return self.env['account.invoice'], error_str

        # Try to find related res.partner record
        partner = self.env['res.partner']
        if partner_ref:
            partner = self.env['res.partner'].sudo().search([('kodas', '=', partner_ref)], limit=1)
            if not partner:
                partner = self.env['res.partner'].sudo().search([('name', '=', partner_ref)], limit=1)

        # If there's only partner reference and related partner is not found, return an error
        if not move_name and partner_ref and not partner:
            error_str = 'Partner not found | Partner with your provided partner identification was not found'
            return self.env['account.invoice'], error_str

        if move_name:
            domain = [('move_name', '=', move_name)]
        else:
            domain = [('reference', '=', reference)]
        if partner:
            domain.append(('partner_id', '=', partner.id))
        invoice = self.env['account.invoice'].sudo().search(domain)
        return invoice, error_str

    @api.model
    def update_domain_search_overridable(self, post):
        """
        Overridable method used to extend the domain
        for account.invoice update operation
        :param post: API post
        :return: account.invoice, error_str
        """
        error_str = str()
        invoice_obj = self.env['account.invoice'].sudo()
        reference, number = post.get('reference'), post.get('number')
        if not number:
            error_str = 'Missing invoice number'
            return False, error_str
        if not reference:
            reference = number
        invoice = invoice_obj.search([
            '|', ('number', '=', number), ('move_name', '=', number), ('type', 'in', ['out_invoice', 'out_refund'])
        ])
        if len(invoice) != 1:
            invoice = invoice_obj.search([
                ('reference', '=', reference), ('type', 'in', ['in_invoice', 'in_refund'])
            ])
        if len(invoice) != 1:
            error_str = 'Invoice with %s number was not found.' % number
            return False, error_str
        return invoice, error_str

    @api.model
    def reconcile_with_earliest_entries(self, invoice):
        """
        If use_credit option is True in create_invoice/update_invoice,
        search for related partner over-payments and try to reconcile the invoice
        with them starting from the oldest payment
        :param invoice: invoice to reconcile
        :return: None
        """
        domain = [('account_id', '=', invoice.account_id.id),
                  ('partner_id', '=', invoice.partner_id.id),
                  ('reconciled', '=', False), ('amount_residual', '!=', 0.0)]
        if invoice.type in ('out_invoice', 'in_refund'):
            domain.extend([('credit', '>', 0), ('debit', '=', 0)])
        else:
            domain.extend([('credit', '=', 0), ('debit', '>', 0)])
        line_ids = self.env['account.move.line'].search(domain, order='date asc')

        for line in line_ids:
            lines = line
            if not tools.float_is_zero(invoice.residual_company_signed, precision_digits=2):
                lines |= invoice.move_id.line_ids.filtered(
                    lambda r: r.account_id.id == invoice.account_id.id)
                if len(lines) > 1:
                    lines.with_context(reconcile_v2=True).reconcile()

    @api.model
    def find_corresponding_taxes(self, line, supplier_invoice):
        """
        Find corresponding taxes for account invoice
        based on passed POST values
        :param line: passed account.invoice.line data
        :param supplier_invoice: indicates whether invoice
            to-be-affected is supplier or not
        :return: account.tax IDs (list)
        """

        # Values are already validated at this point

        # If the value is zero, we still want to apply included/excluded tax type based on this field
        prices_with_vat = isinstance(line.get('price_with_vat'), (float, int))
        invoice_vat_code = line.get('vat_code')
        if not invoice_vat_code:
            return []

        if invoice_vat_code and ' ' not in invoice_vat_code:
            invoice_vat_code = invoice_vat_code.upper()

        # Check for deductible/nondeductible values
        if invoice_vat_code and invoice_vat_code[-1] == 'N':
            invoice_vat_code = invoice_vat_code[:-1]
            nondeductible = True
        else:
            nondeductible = False
        if invoice_vat_code and invoice_vat_code.endswith('NP'):
            invoice_vat_code = invoice_vat_code[:-2]
            nondeductible_profit = True
            nondeductible = True
        else:
            nondeductible_profit = False

        base_tax_domain = [('code', '=', invoice_vat_code),
                           ('nondeductible', '=', nondeductible),
                           ('nondeductible_profit', '=', nondeductible_profit)]

        # Check for price include option
        base_tax_domain += \
            [('price_include', '=', True)] if prices_with_vat else [('price_include', '=', False)]
        # Check for type tax use
        base_tax_domain += \
            [('type_tax_use', '=', 'purchase')] if supplier_invoice else [('type_tax_use', '=', 'sale')]

        tax_ids = self.sudo().env['account.tax'].search(base_tax_domain).ids
        return tax_ids

    @api.model
    def find_or_create_partner(self, partner_data):
        """
        Find or create partner when using create_invoice/update_invoice method
        :param partner_data: partner data passed via API
        :return: res.partner, error_str
        """
        ResPartner = self.env['res.partner'].sudo()
        AccountAccount = self.env['account.account'].sudo()
        error_str = str()
        company = self.env.user.sudo().company_id
        api_allow_empty_partner_code = company.api_allow_empty_partner_code
        api_woocommerce = company.api_woocommerce_integration

        partner_code = (partner_data.get('company_code') or '').strip()
        partner_vat = (partner_data.get('vat_code') or '').strip()
        is_company = partner_data.get('is_company', False)
        partner_email = (partner_data.get('email') or '').strip()

        partner_name = (partner_data.get('name') or '').strip()
        if not partner_name:
            error_str = 'Missing partner name'
            return False, error_str

        country_code = partner_data.get('country', str()) or 'LT'
        country = self.env['res.country'].sudo().search([('code', '=', country_code)], limit=1)
        if not country:
            error_str = 'Incorrect country code'
            return False, error_str

        if partner_vat and not ResPartner.vies_vat_check(country_code.lower(), partner_vat):
            partner_vat = ''
        # Regex match is done based on guess_partner_code_type() method
        if partner_code and ((is_company and not partner_code.isdigit() and country_code == 'LT') or
                             (not is_company and not re.match(r'[0-9a-zA-z()]*$', partner_code))):
            partner_code = ''

        # WooCommerce plugin sets is_company parameter by checking if both company AND VAT codes are specified
        # Company code is enough to tell if partner is a company
        if api_woocommerce and partner_code and not is_company and country_code != 'LT':
            is_company = True
        if is_company and not partner_code and (not api_allow_empty_partner_code or country_code == 'LT'):
            error_str = 'Missing or invalid partner company_code'
            return False, error_str
        partner = False
        if partner_code:
            partner = ResPartner.search([('kodas', '=', partner_code)], limit=1)
        # If partner is found by company code but VAT codes are not matching, search by VAT code provided, if not found,
        # create a new partner. Do not search by company name as it will match an existing partner with wrong VAT code
        different_vats = True if partner and partner.vat and partner_vat and partner.vat != partner_vat else False
        if different_vats or (not partner and partner_vat):
            partner = ResPartner.search([('vat', '=', partner_vat)], limit=1)
            # If partner code (kodas) is specified check if the partner has it set as the code
            if partner and partner_code and partner.kodas and partner.kodas != partner_code:
                vat_code_type = 'company' if is_company else 'personal'
                error_str = 'The partner with the provided VAT code ({}) has a different {} code than the one that ' \
                            'has been specified in the request'.format(partner_vat, vat_code_type)
                return False, error_str
        if not partner and partner_name and not different_vats:
            partner = ResPartner.search([('name', '=', partner_name)], limit=1)
        # Check when only partner_name and email are provided
        partner_name_only = True if partner_name and not partner_code and not partner_vat else False
        different_emails = True if partner and partner.email and partner_email and partner.email != partner_email \
            else False
        if partner_name_only and different_emails:
            partner = ResPartner.search([('name', '=', partner_name), ('email', '=', partner_email)], limit=1)
        if partner:
            bank, error_str = self.create_partner_bank(partner, partner_data.get('bank_account'))
            return partner, error_str

        language = partner_data.get('language', 'LT')
        if language not in LANGUAGE_MAPPING:
            error_str = 'Incorrect partner language'
            return False, error_str

        partner_vals = {
            'name': partner_name,
            'is_company': is_company,
            'kodas': partner_code,
            'vat': partner_vat,
            'street': partner_data['street'] if 'street' in partner_data else False,
            'city': partner_data['city'] if 'city' in partner_data else False,
            'zip': partner_data['zip'] if 'zip' in partner_data else False,
            'country_id': country.id,
            'lang': LANGUAGE_MAPPING[language],
            'phone': partner_data['phone'] if 'phone' in partner_data else False,
            'email': partner_email,
            'property_account_receivable_id': AccountAccount.search([('code', '=', '2410')], limit=1).id,
            'property_account_payable_id': AccountAccount.search([('code', '=', '4430')], limit=1).id,
        }
        # Add extra partner values
        self.add_partner_tags(data=partner_data, partner_vals=partner_vals)
        try:
            partner = ResPartner.with_context(skip_vat_constrains=True).create(partner_vals)
            bank, error_str = self.create_partner_bank(partner, partner_data.get('bank_account'))
            return partner, error_str
        except Exception as e:
            _logger.info('ROBO API EXCEPTION: %s' % e)
            error_str = 'Could not create partner.'
            return False, error_str

    @api.model
    def add_partner_tags(self, data, partner_vals):
        """
        Add extra values to partner value dict
        (tags - res.partner.category and partner_category - partner.category)
        :param data: partner data passed via API
        :param partner_vals: values of to-be-created res.partner
        :return: None
        """
        if data.get('tags'):
            tag_ids = []
            if not isinstance(data['tags'], list):
                return
            for tag in data['tags']:
                part_tag = self.env['res.partner.category'].search([('name', '=', tag)])
                if part_tag:
                    tag_ids.append((4, part_tag.id))
                else:
                    tag_ids.append((0, 0, {'name': tag}))
            partner_vals['category_id'] = tag_ids
        if data.get('partner_category'):
            part_categ_id = self.env['partner.category'].search([('name', '=', data.get('partner_category'))])
            if not part_categ_id:
                part_categ_id = self.env['partner.category'].create({'name': data.get('partner_category')})
            partner_vals['partner_category_id'] = part_categ_id.id

    @api.model
    def find_or_create_product(self, product_data):
        """
        Find or create product when using create_invoice/update_invoice method
        :param product_data: API post
        :return: product.product, error_str
        """
        ProductProduct = self.env['product.product']
        ProductCategory = self.env['product.category']

        error_str = str()
        company = self.env.user.sudo().company_id
        api_default_product_type = company.api_default_product_type
        api_allow_new_products = company.api_allow_new_products
        allow_empty = not company.prevent_empty_product_code

        product_code = (product_data.get('product_code') or '').strip()
        product_name = (product_data.get('product') or '').strip()
        product_id = product_data['product_id'] if type(product_data.get('product_id') or False) == int else False

        if not product_code and not product_name and not product_id:
            error_str = 'Missing invoice lines'
            return False, error_str

        product = ProductProduct

        if product_id:
            # Do not use browse with random value (or use browse().exists()), because it always finds a record
            # no matter what int you pass (env['product.product'].browse(9999))
            product = ProductProduct.search([('id', '=', product_id), ('categ_id.skip_api_sync', '=', False)])
        if product_code:
            if not product or (product.default_code and product.default_code != product_code):
                product = ProductProduct.search([('default_code', '=', product_code),
                                                 ('categ_id.skip_api_sync', '=', False)], limit=1)

        if product_name:
            # Check if product name provided matches with product found if product is not identified by product_code
            if product and not product_code and product.with_context(lang='lt_LT').name != product_name \
                    and product.with_context(lang='en_US').name != product_name:
                product = False
            if not product:
                product = ProductProduct.with_context(lang='lt_LT').search([('name', '=', product_name),
                                                                            ('categ_id.skip_api_sync', '=', False)],
                                                                           limit=1)
            if not product:
                product = ProductProduct.with_context(lang='en_US').search([('name', '=', product_name),
                                                                            ('categ_id.skip_api_sync', '=', False)],
                                                                           limit=1)

        if product:
            return product, error_str

        if not product_name:
            error_str = 'Missing product name'
            return False, error_str

        if api_allow_new_products:
            if api_default_product_type == 'cost':
                product_type = 'service'
                acc_product_type = 'product'
                category = self.env.ref('l10n_lt.product_category_30', raise_if_not_found=False)
                if not category:
                    category = ProductCategory.with_context(lang='lt_LT'). \
                        search([('name', '=', 'Parduotų prekių savikaina')], limit=1)
            elif api_default_product_type == 'service':
                product_type = 'service'
                acc_product_type = 'service'
                category = self.env.ref('l10n_lt.product_category_2', raise_if_not_found=False)
                if not category:
                    category = ProductCategory.with_context(lang='lt_LT'). \
                        search([('name', '=', 'Parduodamos paslaugos')], limit=1)
            elif api_default_product_type == 'product':
                product_type = 'product'
                acc_product_type = 'product'
                category = self.env.ref('l10n_lt.product_category_1', raise_if_not_found=False)
                if not category:
                    category = ProductCategory.with_context(lang='lt_LT'). \
                        search([('name', '=', 'Prekės')], limit=1)
            else:
                error_str = 'Default product type is not selected.'
                return False, error_str
            if not category:
                if not tools.config.get('test_enable'):
                    self.env.cr.rollback()
                    self.env['robo.bug'].sudo().create({'user_id': self.env.user.id,
                                                        'error_message': 'Missing category',
                                                        })
                    self.env.cr.commit()
                error_str = 'Missing product category.'
                return False, error_str

            if not product_code and not allow_empty:
                error_str = 'Missing product code'
                return False, error_str

            product_vals = {
                'name': product_name,
                'default_code': product_code,
                'categ_id': category.id,
                'type': product_type,
                'sale_ok': True,
                'acc_product_type': acc_product_type,
            }
        else:
            error_str = 'New product creation from API is not allowed.'
            return False, error_str

        try:
            product = ProductProduct.create(product_vals)
            return product, error_str
        except Exception as e:
            _logger.info('ROBO API EXCEPTION: %s' % e)
            error_str = 'Could not create new product.'
            return False, error_str

    @api.model
    def create_attachment(self, attachment_data, invoice_id=None):
        IrAttachment = self.env['ir.attachment']
        error_str = str()

        file_data = (attachment_data.get('file_data') or '').strip()
        if not file_data:
            error_str = 'File data not provided'
            return False, error_str

        # Check if given data is base64 encoded
        expression = "^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)?$"
        if not re.match(expression, file_data):
            error_str = 'Wrong file format'
            return False, error_str

        invoice_file_name = (attachment_data.get('invoice_number') or
                             (attachment_data.get('invoice_reference') or '')).strip()
        file_name = (attachment_data.get('file_name') or invoice_file_name).strip()
        attachment_values = {
            'type': 'binary',
            'name': file_name + '.pdf',
            'datas_fname': file_name + '.pdf',
            'datas': file_data,
        }
        if invoice_id:
            attachment_values.update({
                'res_model': 'account.invoice',
                'res_id': invoice_id,
            })
        try:
            attachment = IrAttachment.create(attachment_values)
        except Exception as e:
            system_error = 'ROBO API EXCEPTION: %s' % e.args[0]
            _logger.info(system_error)
            error_str = 'The attachment could not be created'
            return False, error_str
        return attachment, error_str

    @api.model
    def find_or_create_analytic_account(self, line_data):
        """
        Find or create analytics when using create_invoice/update_invoice/create_accounting_entries method
        :param line_data: API post
        :return: account.analytic.account, error_str
        """
        robo_analytic_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_analytic'), ('state', 'in', ['installed', 'to upgrade'])])
        error_str = str()
        if robo_analytic_installed:
            analytic_code = line_data.get('analytic_code', False)
            AccountAnalyticAccount = self.env['account.analytic.account'].sudo()
            if analytic_code:
                analytic_account = AccountAnalyticAccount.search([('code', '=', analytic_code)], limit=1)
                if not analytic_account:
                    try:
                        analytic_account = AccountAnalyticAccount.create({
                            'code': analytic_code,
                            'name': analytic_code
                        })
                    except Exception as e:
                        _logger.info('ROBO API EXCEPTION: %s' % e)
                        error_str = 'Could not create new analytic account.'
                        return False, error_str
                return analytic_account, error_str
        return False, error_str

    @api.model
    def find_or_create_intrastat_code(self, data):
        """
        Find or create intrastat code when using
        create_product/update_product/create_product_category/update_product_category methods
        :param data: API post
        :return: report.intrastat.code, error_str
        """
        IntrastatCode = self.env['report.intrastat.code'].sudo()
        error_str = str()

        report_intrastat_code = IntrastatCode
        intrastat_code = (data.get('intrastat_code') or '').strip()
        intrastat_description = (data.get('intrastat_description') or '').strip()
        if intrastat_code:
            report_intrastat_code = IntrastatCode.search([('name', '=', intrastat_code)], limit=1)
            if not report_intrastat_code:
                try:
                    report_intrastat_code = IntrastatCode.create({
                        'name': intrastat_code,
                        'description': intrastat_description,
                    })
                except Exception as e:
                    _logger.info('ROBO API EXCEPTION: %s' % e)
                    error_str = 'Could not create new intrastat code.'
                    return False, error_str
        return report_intrastat_code, error_str

    @api.model
    def find_invoice(self, invoice_data):
        AccountInvoice = self.env['account.invoice'].sudo()
        error_str = str()

        invoice_id = invoice_data['invoice_id'] if type(invoice_data.get('invoice_id') or False) == int else False
        invoice_number = (invoice_data.get('invoice_number') or '').strip()
        invoice_reference = (invoice_data.get('invoice_reference') or '').strip()
        comment = (invoice_data.get('comment') or '').strip()
        partner_code = (invoice_data.get('partner_code') or '').strip()

        # Check all of the constraints
        if not invoice_id and not invoice_number and not invoice_reference and not comment:
            error_str = 'Please provide at least one identifying field: invoice_id, invoice_reference, ' \
                        'invoice_number, comment'
            return False, error_str

        invoice = AccountInvoice
        if invoice_reference and not invoice_number and not invoice_id and not comment:
            if not partner_code:
                error_str = 'Partner code is required when only invoice_reference is passed as a searchable'
                return False, error_str
            partner = self.env['res.partner'].search([('kodas', '=', partner_code)], limit=1)
            if not partner:
                error_str = 'Did not find related partner in the system, which is required to check the invoice when ' \
                            'using only reference'
                return False, error_str

            # Check the invoice by reference
            invoice = AccountInvoice.search(
                [('reference', '=', invoice_reference), ('partner_id', '=', partner.id)], limit=1)

        if invoice_id:
            invoice = AccountInvoice.search([('id', '=', invoice_id)], limit=1)
        if not invoice and invoice_number:
            invoice = AccountInvoice.search([('number', '=', invoice_number)], limit=1)
        if not invoice and comment:
            invoice = AccountInvoice.search([('comment', '=', comment)], limit=1)

        if not invoice:
            error_str = 'Invoice not found'
            return False, error_str

        return invoice, error_str

    @api.model
    def check_invoice_identifying_fields(self, invoice_data):
        error_str = str()

        invoice_id = invoice_data['invoice_id'] if type(invoice_data.get('invoice_id') or False) == int else False
        invoice_number = (invoice_data.get('invoice_number') or '').strip()
        invoice_reference = (invoice_data.get('invoice_reference') or '').strip()
        comment = (invoice_data.get('comment') or '').strip()
        partner_code = (invoice_data.get('partner_code') or '').strip()

        # Check all of the constraints
        if not invoice_id and not invoice_number and not invoice_reference and not comment:
            error_str = 'Please provide at least one identifying field: invoice_id, invoice_reference, ' \
                        'invoice_number, comment'
            return error_str

        if invoice_reference and not invoice_number and not invoice_id and not comment:
            if not partner_code:
                error_str = 'Partner code is required when only invoice_reference is passed as a searchable'
                return error_str

        return error_str

    @api.model
    def get_invoice_data(self, invoice, include_pdf):
        type_mapper = {
            'out_refund': 'Client Invoice - Refund',
            'out_invoice': 'Client Invoice',
            'in_refund': 'Supplier Invoice - Refund',
            'in_invoice': 'Supplier Invoice',
        }
        # Check whether robo stock is installed
        robo_stock_installed = self.env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])])
        # Only used if stock is installed
        total_gp = total_cost = 0.0

        # Prepare account invoice line data to return
        invoice_lines = []
        for line in invoice.invoice_line_ids:
            # Base data
            line_data = {
                'product': line.product_id.name or line.name,
                'price': line.price_unit_tax_excluded,
                'qty': line.quantity,
                'vat_code': line.mapped('invoice_line_tax_ids.code'),
                'vat': tools.float_round(
                    line.price_unit_tax_included - line.price_unit_tax_excluded, precision_digits=2),
                'price_with_vat': line.price_unit_tax_included,
            }
            # If line product type is 'product' and stock is installed,
            # append two extra fields to the line dict
            if line.product_id.type == 'product' and robo_stock_installed:
                line_data.update({
                    'gross_profit': line.gp,
                    'cost': line.cost,
                })
                # Accumulate totals
                total_gp += line.gp
                total_cost += line.cost

            invoice_lines.append(line_data)

        # TODO: LT Characters are represented as bytes, e.g 'S/0415skaitos' for 'Sąskaitos' - Fix that
        invoice_data = {
            'state': str(dict(invoice._fields['state']._description_selection(self.env)).get(invoice.state)),
            'number': invoice.number,
            'date_invoice': invoice.date_invoice,
            'date_due': invoice.date_due,
            'currency': invoice.currency_id.name,
            'partner_name': invoice.partner_id.name,
            'partner_code': invoice.partner_id.kodas,
            'type': type_mapper.get(invoice.type),
            'invoice_lines': invoice_lines,
            'payments': [{
                'payer': line.partner_id.name or str(),
                'amount': abs(line.balance),
                'date': line.date,
                'ref': line.ref or str(),
                'name': line.name or str(),
                'journal_code': line.journal_id.code,
                'journal_name': line.journal_id.name,
            } for line in invoice.payment_move_line_ids],
            'amount_total_company_currency': invoice.amount_total_company_signed,
            'amount_untaxed_company_currency': invoice.amount_untaxed_signed,
            'amount_tax_company_currency': invoice.amount_tax_signed,
            'amount_residual_company_currency': invoice.residual_company_signed,
            'amount_total_invoice_currency': invoice.amount_total_signed,
            'amount_untaxed_invoice_currency': invoice.amount_untaxed,
            'amount_tax_invoice_currency': invoice.amount_tax,
            'amount_residual_invoice_currency': invoice.residual_signed,
        }

        # If stock is installed, always display total cost and gp amounts
        if robo_stock_installed:
            invoice_data.update({
                'amount_total_cost': total_cost,
                'amount_total_gross_profit': total_gp,
            })

        if include_pdf:
            action = invoice.invoice_print()
            pdf_base64 = base64.b64encode(self.env['ir.actions.report.xml'].render_report(
                [invoice.id], action['report_name'], action['data'])[0])
            invoice_data.update({
                'pdf': pdf_base64
            })

        return invoice_data

    @api.model
    def get_deferred_data(self, line_post, invoice_type, product_account):
        """
        Get deferred data to write to invoice line
        :param line_post: Invoice line data posted to API endpoint
        :param invoice_type: Type of invoice
        :param product_account: Invoice line product account
        :return: Dictionary of defer data
        """
        AccountAccount = self.env['account.account']
        data = {}
        is_deferred = line_post.get('deferred')
        if not is_deferred:
            return data, str()

        defer_start_date = line_post.get('defer_start_date')
        error_str = check_date_format(defer_start_date, 'defer_start_date')
        if error_str:
            return data, error_str
        defer_number_of_months = line_post.get('defer_number_of_months')
        try:
            defer_number_of_months = int(defer_number_of_months)
        except (ValueError, TypeError):
            return data, 'Incorrect defer number of months period'

        account_code = '492' if invoice_type in ['out_invoice', 'out_refund'] else '291'
        defer_account = AccountAccount.search([('code', '=', account_code)], limit=1)

        if not defer_account:
            return data, 'Defer account not found'

        data.update({
            'deferred_line_id': [(0, 0, {
                'date_from': defer_start_date,
                'number_periods': defer_number_of_months,
                'account_id': product_account.id
            })],
            'deferred': True,
            'account_id': defer_account.id
        })
        return data, str()

    @api.model
    def _process_invoice_payments(self, invoice, payments_data):
        # Process provided payment data
        if isinstance(payments_data, list):
            payments = payments_data
        elif isinstance(payments_data, dict):
            payments = [payments_data]
        else:
            payments = list()

        if not payments:
            return f_resp(at.API_SUCCESS)

        currency_obj = self.env['res.currency']
        journal_obj = self.env['account.journal']
        account_move_obj = self.env['account.move']
        company = self.env.user.sudo().company_id

        for payment in payments:
            # Check residual after each loop of the payments,
            # If residual is zero, do not try to create new moves
            if tools.float_is_zero(invoice.residual, precision_digits=2):
                continue

            payment_journal_code = (payment.get('journal_code') or 'CARD').upper()
            payment_journal_name = payment.get('journal_name') or 'Payments'

            if len(payment_journal_code) > 5:
                return f_resp(at.API_INCORRECT_DATA, 'Failed preparing payment. Wrong journal code: "%s". '
                                                     'Code length cannot exceed 5 characters' % payment_journal_code)
            payment_journal = journal_obj.search([('code', '=', payment_journal_code)], limit=1)
            if not payment_journal:
                if not payment_journal_name:
                    return f_resp(at.API_INCORRECT_DATA,
                                  'Failed preparing payment. Journal with code "%s" not found. '
                                  'Please provide a journal_name' % payment_journal_code)
                payment_journal = journal_obj.search([('name', '=', payment_journal_name)], limit=1)
            if not payment_journal:
                payment_journal = journal_obj.create({
                    'name': payment_journal_name,
                    'code': payment_journal_code,
                    'type': 'bank',
                })
            if not payment_journal:
                return f_resp(at.API_NOT_FOUND, 'Failed preparing payment. Payment journal was not found')

            # Get payer property
            payer = str(payment.get('payer') or '').strip()
            if not payer:
                return f_resp(at.API_INCORRECT_DATA, 'Missing or incorrect payer property')

            payer_partner = None
            if company.api_create_payer_partners:
                payer_partner, error_str = self.find_or_create_partner({'name': payer})
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)

            if 'amount' in payment and isinstance(payment['amount'], tuple([int, float, long])):
                amount = abs(payment['amount'])
            else:
                return f_resp(at.API_INCORRECT_DATA, 'Missing or incorrect payment amount field.')
            payment_date = payment.get('date')
            if payment_date:
                error_str = check_date_format(payment_date, 'date')
                if error_str:
                    return f_resp(at.API_INCORRECT_DATA, error_str)
                date = payment_date
            else:
                return f_resp(at.API_INCORRECT_DATA, 'Missing payment date.')

            # check currency
            payment_currency_id = False
            payment_amount_currency = 0.0
            if 'currency' in payment and payment['currency'] != company.currency_id.name:
                payment_currency_id = currency_obj.search([('name', '=', payment['currency'])], limit=1)
                if payment_currency_id:
                    payment_amount_currency = amount
                    amount = payment_currency_id.with_context(date=date).compute(amount, company.currency_id)
                else:
                    return f_resp(at.API_INCORRECT_DATA, 'Incorrect payment currency.')

            if 'ref' in payment and payment['ref']:
                ref = unicode(payment['ref'])
            else:
                ref = invoice.number
            ref = u'Apmokėjo ' + payer + u' - ' + ref
            if 'name' in payment and payment['name']:
                name = unicode(payment['name'])
            else:
                name = u'Mokėjimas ' + payer
            lines = []
            line1_vals = {
                'name': name,
                'account_id': invoice.account_id.id,
                'date': date,
            }

            if payment_currency_id:
                line1_vals['currency_id'] = payment_currency_id.id
                sign = -1.0 if invoice.type in ['out_invoice', 'in_refund'] else 1.0
                line1_vals['amount_currency'] = payment_amount_currency * sign

            if invoice.type in ['out_invoice', 'in_refund']:
                line1_vals['credit'] = amount
                line1_vals['debit'] = 0.0
            else:
                line1_vals['debit'] = amount
                line1_vals['credit'] = 0.0
            line2_vals = {
                'name': name,
                'date': date,
                'partner_id': payer_partner.id if payer_partner else None
            }
            if payment_currency_id:
                line2_vals['currency_id'] = payment_currency_id.id
                sign = 1.0 if invoice.type in ['out_invoice', 'in_refund'] else -1.0
                line2_vals['amount_currency'] = payment_amount_currency * sign

            if invoice.type in ['out_invoice', 'in_refund']:
                line2_vals['debit'] = amount
                line2_vals['credit'] = 0.0
                line2_vals['account_id'] = payment_journal.default_debit_account_id.id
            else:
                line2_vals['credit'] = amount
                line2_vals['debit'] = 0.0
                line2_vals['account_id'] = payment_journal.default_credit_account_id.id
            lines.append((0, 0, line1_vals))
            lines.append((0, 0, line2_vals))
            move_vals = {
                'ref': ref,
                'line_ids': lines,
                'journal_id': payment_journal.id,
                'date': date,
                'partner_id': invoice.partner_id.id,
            }
            move_id = account_move_obj.create(move_vals)
            move_id.post()
            line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice.account_id.id)
            line_ids |= invoice.move_id.line_ids.filtered(
                lambda r: r.account_id.id == invoice.account_id.id)
            if len(line_ids) > 1:
                line_ids.with_context(reconcile_v2=True).reconcile()
        return f_resp(at.API_SUCCESS)


RoboAPIBase()
