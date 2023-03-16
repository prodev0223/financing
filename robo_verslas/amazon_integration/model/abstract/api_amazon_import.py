# -*- coding: utf-8 -*-

from odoo import models, api, tools, exceptions, _
from dateutil.parser import parse
from datetime import datetime
import logging
from dateutil.relativedelta import relativedelta
from ... import amazon_tools as at
from six import iteritems
import mws
import time
import ssl
import pytz

_logger = logging.getLogger(__name__)


class APIAmazonImport(models.AbstractModel):
    """
    Abstract model that is used for connections to Amazon API endpoints
    """
    _name = 'api.amazon.import'

    # API Connector // ------------------------------------------------------------------------------------------------

    @api.model
    def test_api(self, access_key, secret_key, account_id, region_code):
        """
        Test API connection with passed key values
        :param access_key: Amazon access key
        :param secret_key: Amazon secret key
        :param account_id: Amazon account ID
        :param region_code: Code of the region that is being tested
        :return: True if API is working, otherwise False
        """
        default_region_code = at.REGION_CODE_TO_DEFAULT[region_code]
        region_marketplaces = at.REGION_TO_MARKETPLACE_IDS_MAPPING[region_code]

        api_data = {'access_key': access_key,
                    'secret_key': secret_key,
                    'account_id': account_id,
                    'region': default_region_code
                    }
        working_api = True
        orders_api = mws.Orders(**api_data)
        try:
            # We try it with order API, because library does not provide any testing methods
            orders_api.list_orders(**{
                'marketplaceids': region_marketplaces,
                'created_after': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            })
        except mws.MWSError:
            working_api = False
        return working_api

    @api.model
    def get_api(self, region, api_type='orders'):
        """
        Connect to external Amazon API using values stored in the res.company as credentials
        :param region: amazon.region record which data is used for the endpoint
        :param api_type: Indicates what kind of API should be connected to ('orders', 'products', 'finances')
        :return: mws API object (object)
        """
        api_obj = None

        # Get amazon config parameters
        account_id = region.amazon_account_id
        access_key = region.amazon_access_key
        secret_key = region.amazon_secret_key
        default_region_code = at.REGION_CODE_TO_DEFAULT[region.code]

        if not account_id or not access_key or not secret_key:
            raise exceptions.UserError(_('Nesukonfigūruoti Amazon API nustatymai!'))

        api_data = {'access_key': access_key,
                    'secret_key': secret_key,
                    'account_id': account_id,
                    'region': default_region_code}
        try:
            if api_type == 'orders':
                api_obj = mws.Orders(**api_data)
            elif api_type == 'products':
                api_obj = mws.Products(**api_data)
            elif api_type == 'finances':
                api_obj = mws.Finances(**api_data)
        except Exception as exc:
            raise exceptions.UserError('Failed to connect to Amazon API. Error - {}'.format(exc.args[0]))
        return api_obj

    @api.model
    def api_throttle_handler(self, api_obj, method, extra_args=None, fail_count=0):
        """
        MWS library opens a new connection each time API is called.
        This method used to handle API throttles -- Each time we get an error
        we call the same function recursively increasing the sleep time before
        calling the API again
        :param api_obj: MWS API object
        :param method: Signifies which endpoint should be accessed
        :param extra_args: Extra arguments passed to API call
        :param fail_count: throttle fail count
        :return: fetched order items, or execute self.order_line_api_throttle_handler() again
        """
        extra_args = {} if extra_args is None else extra_args  # Prevent mutable default args
        try:
            if method == 'orders':
                api_response = api_obj.list_orders(**extra_args)
            elif method == 'financial_operations':
                api_response = api_obj.list_financial_events(**extra_args)  # amazon_order_id=order_id
            elif method == 'categories':
                api_response = api_obj.get_product_categories_for_asin(**extra_args)
            elif method == 'products':
                api_response = api_obj.get_matching_product_for_id(**extra_args)
            elif method == 'order_items':
                api_response = api_obj.list_order_items(**extra_args)
            else:
                raise exceptions.UserError(_('Incorrect Amazon endpoint %s') % method)
        except Exception as exc:
            fail_count += 1
            if fail_count > 15:
                raise exceptions.UserError(
                    _('Amazon API throttled after 10 tries. Endpoint - {}, Error - {}').format(method, exc.args[0]))
            # On API throttle, use time sleep which grows on each failed try
            time.sleep(5 * fail_count)
            return self.api_throttle_handler(api_obj, method, extra_args, fail_count)
        return api_response

    # Main API methods // ---------------------------------------------------------------------------------------------

    @api.model
    def api_fetch_orders_prep(self, date_to=None):
        """
        Prepare to fetch Amazon for each region.
        Call main method by passing each configured
        region in a loop.
        :return: None
        """
        regions = self.env['amazon.region'].search([('api_state', '=', 'working'), ('activated', '=', True)])
        final_order_list = []
        for region in regions:
            order_list = self.api_fetch_orders(region, date_to)
            final_order_list.extend(order_list)
        self.set_sync_date()
        return final_order_list

    @api.model
    def api_fetch_orders(self, region, date_to=None):
        """
        Import Amazon orders using specific API endpoint
        Orders are fetched using predefined marketplace IDs and sync date
        Fetched data is validated/grouped and prepared for record creation
        :param region: amazon.region record for which the operation
        :param date_to: date to which orders should be fetched (optional)
        should be executed
        :return: fetched order list
        """

        # Get import sync date and connect to orders API
        sync_date, initial_fetch = self.get_sync_date()

        # Create SSL context
        if hasattr(ssl, '_create_unverified_context'):
            ssl._create_default_https_context = ssl._create_unverified_context

        order_api = self.get_api(region, api_type='orders')
        finances_api = self.get_api(region, api_type='finances')
        product_api = self.get_api(region, api_type='products')
        sum_integration = self.sudo().env.user.company_id.amazon_integration_type == 'sum'

        # get_sync_date will already raise an error, thus we can strp-time safely here
        threshold_date_dt = datetime.strptime(self.sudo().env.user.company_id.amazon_accounting_threshold_date,
                                              tools.DEFAULT_SERVER_DATE_FORMAT).replace(tzinfo=pytz.UTC)
        try:
            sync_date_dt = datetime.strptime(sync_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        except ValueError:
            sync_date_dt = datetime.strptime(sync_date, tools.DEFAULT_SERVER_DATE_FORMAT)

        if initial_fetch:
            # Take a bigger gap on initial fetch
            sync_date_dt = sync_date_dt - relativedelta(months=1)

        # If date to is not passed, use utc now
        if date_to:
            try:
                temp_date_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                temp_date_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            temp_date_dt = datetime.utcnow()

        order_list = []
        fetched_orders = []
        region_marketplaces = at.REGION_TO_MARKETPLACE_IDS_MAPPING[region.code]
        # Order API is limited to 100 orders per request so we fetch them day by day, from utcnow
        # till the sync date, subtracting the day on each loop
        while temp_date_dt > sync_date_dt:
            updated_before = temp_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            updated_after = (temp_date_dt - relativedelta(days=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            orders = self.api_throttle_handler(
                order_api, method='orders',
                extra_args={'marketplaceids': region_marketplaces,
                            'lastupdatedafter': updated_after,
                            'lastupdatedbefore': updated_before}
            )
            if orders:

                # Try parsing orders from the received API response
                # if the matched structure does not exist, raise an error
                try:
                    order_list_resp = orders.parsed.Orders.Order
                except (AttributeError, KeyError):
                    # Do not raise any exceptions here, if Orders
                    # is empty, it does not contain .Order field
                    order_list_resp = []

                if not isinstance(order_list_resp, list):
                    order_list_resp = [order_list_resp]
                # Several product ID's are used throughout the API...
                # So we have to fetch one using another one and map it
                item_id_to_asin_mapping = {}
                for order_data in order_list_resp:

                    # Do not fetch orders that are earlier than threshold date
                    order_time = self.parse_date_value(
                        self.get_value(order_data, 'PurchaseDate'), return_dt=True)

                    # Fetch order status, and import only shipped orders
                    order_status = self.get_value(order_data, 'OrderStatus')
                    if order_status != 'Shipped':
                        continue

                    # Get order ID from fetched data, if it does not exist, raise an error
                    order_id = self.get_value(order_data, 'AmazonOrderId')
                    if not order_id:
                        raise exceptions.ValidationError(_('Amazon order API returned malformed query'))

                    if order_id in fetched_orders or self.env['amazon.order'].search_count(
                            [('order_id', '=', order_id)]):
                        continue
                    fetched_orders.append(order_id)

                    # Use different API call to fetch ASIN's, different product ID.
                    order_item_resp = self.api_throttle_handler(
                        order_api, method='order_items', extra_args={'amazon_order_id': order_id})

                    try:
                        order_items_data = order_item_resp.parsed.OrderItems.OrderItem
                    except (AttributeError, KeyError):
                        raise exceptions.ValidationError(_('Amazon order line API returned malformed query'))

                    if not isinstance(order_items_data, list):
                        order_items_data = [order_items_data]
                    for item_data in order_items_data:
                        item_asin = self.get_value(item_data, 'ASIN')
                        item_order_id = self.get_value(item_data, 'OrderItemId')

                        # We do not fetch further product information in 'Sum' integration
                        # But we save ASIN and ext_id values of the product
                        if not sum_integration and not self.env['amazon.product'].search_count(
                                [('asin_product_code', '=', item_asin)]):
                            self.fetch_create_amazon_product(product_api, order_data, item_data)

                        if item_order_id not in item_id_to_asin_mapping:
                            item_id_to_asin_mapping[item_order_id] = item_asin
                        else:
                            if item_id_to_asin_mapping[item_order_id] != item_asin:
                                raise exceptions.ValidationError(_('Amazon order line API returned malformed query'))

                    # Fetch financial events
                    financial_events_resp = self.api_throttle_handler(
                        finances_api, method='financial_operations', extra_args={'amazon_order_id': order_id})

                    order_lines = []
                    # Prepare base order values
                    order_values = {
                        'order_id': order_id,
                        'buyer_email': self.get_value(order_data, 'BuyerEmail'),
                        'fulfillment_channel': self.get_value(order_data, 'FulfillmentChannel'),
                        'business_order': self.parse_bool_value(self.get_value(order_data, 'IsBusinessOrder')),
                        'premium_order': self.parse_bool_value(self.get_value(order_data, 'IsPremiumOrder')),
                        'quantity_not_shipped': self.get_value(
                            order_data, 'NumberOfItemsUnshipped', expected_type=float),
                        'marketplace_code': self.get_value(order_data, 'MarketplaceId'),
                        'currency_code': self.get_value(order_data.get('OrderTotal'), 'CurrencyCode'),
                        'ext_order_status': order_status,
                        'ext_order_type': self.get_value(order_data, 'OrderType'),
                        'marketplace_name': self.get_value(order_data, 'SalesChannel'),
                        'amazon_order_line_ids': order_lines
                    }

                    # Fetch refund events
                    try:
                        refund_events = financial_events_resp.parsed.FinancialEvents.RefundEventList
                    except (AttributeError, KeyError):
                        raise exceptions.ValidationError(_('Amazon order line API returned malformed query'))

                    # If refund events exist, create separate order for refund lines
                    if refund_events:
                        refund_list = refund_events.ShipmentEvent
                        if not isinstance(refund_list, list):
                            refund_list = [refund_list]
                        for refund_order in refund_list:
                            refund_time_dt = self.parse_date_value(
                                self.get_value(refund_order, 'PostedDate'), return_dt=True)

                            # We get the correct refund time here, skip it on threshold cross
                            if threshold_date_dt > refund_time_dt:
                                continue

                            refund_time = refund_time_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                            # If refund with the same parent ID exists on the same time -- Skip it
                            if self.env['amazon.order'].search_count(
                                    [('order_id', '=', order_id),
                                     ('order_time', '=', refund_time),
                                     ('refund_order', '=', True)]):
                                continue

                            item_adjustments = refund_order.ShipmentItemAdjustmentList.ShipmentItem
                            # It's suggested to use isinstance on single-item refunds in official library documentation
                            if not isinstance(item_adjustments, list):
                                item_adjustments = [item_adjustments]

                            refund_lines = []
                            for item_adjustment in item_adjustments:
                                self.add_order_lines(
                                    item_adjustment, refund_lines, item_id_to_asin_mapping, refund=True)
                            refund_values = order_values.copy()
                            refund_values.update({
                                'amazon_order_line_ids': refund_lines,
                                'refund_order': True,
                                'order_time': refund_time
                                 })
                            order_list.append(refund_values)

                    # Check whether order is not yet in the system, if it is, skip it
                    # We need to fetch refund data, which can be updated, before continuing
                    if self.env['amazon.order'].search_count([('order_id', '=', order_id)]):
                        continue

                    # Fetch shipping events, which act as order lines and further as account.invoice lines
                    try:
                        shipment_events_resp = financial_events_resp.parsed.FinancialEvents.ShipmentEventList
                    except (AttributeError, KeyError):
                        raise exceptions.ValidationError(_('Amazon order line API returned malformed query'))

                    if shipment_events_resp:
                        shipment_events = shipment_events_resp.ShipmentEvent
                        if not isinstance(shipment_events, list):
                            shipment_events = [shipment_events]
                        for shipment_event in shipment_events:
                            # Fetch the latest order date from the shipment events
                            shipment_date = self.parse_date_value(
                                self.get_value(shipment_event, 'PostedDate'), return_dt=True)
                            if shipment_date and shipment_date > order_time:
                                order_time = shipment_date
                            shipment_items = shipment_event.ShipmentItemList.ShipmentItem
                            # It's suggested to use isinstance on single-item refunds in official library documentation
                            if not isinstance(shipment_items, list):
                                shipment_items = [shipment_items]
                            for shipment_item in shipment_items:
                                self.add_order_lines(shipment_item, order_lines, item_id_to_asin_mapping)

                    # Only skip here, after we get the latest -- real order time
                    if threshold_date_dt > order_time:
                        continue

                    # Write order date
                    order_values['order_time'] = order_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    # Add fetched values to the list
                    order_list.append(order_values)
            temp_date_dt -= relativedelta(days=1)
        return order_list

    @api.model
    def add_order_lines(self, item_node, order_lines, item_to_asin, refund=False):
        """
        Parse order line values from passed parent item node and add them to the
        record_set. Lines are of two types -- refund and sale
        :param item_node: Amazon API dict node
        :param item_to_asin: product code mapping dict
        :param order_lines: list to append new lines to
        :param refund: signifies whether line is refund or not
        :return: None
        """
        def add_spec_line(line_list, line_name, line_type, line_total, amount_tax=0.0):
            """
            Inner method to add special lines that are always of 1 quantity and contain
            no product -- (Shipping/Fee/Promotion lines)
            """
            line_values = {
                'ext_line_name': line_name,
                'line_amount': line_total,
                'amount_tax': amount_tax,
                'line_type': line_type,
            }
            line_list.append((0, 0, line_values))

        base_values = {
            at.MAIN_COMPONENT_NAME: 0.0,
            at.MAIN_COMPONENT_TAX_NAME: 0.0,
            at.SHIPPING_CHARGE_NAME: 0.0,
            at.SHIPPING_COMPONENT_TAX_NAME: 0.0,
            at.GIFT_COMPONENT_NAME: 0.0,
            at.GIFT_COMPONENT_TAX_NAME: 0.0
        }

        # Check for main line components, split amounts based on whether component is tax or not
        charge_adjustments = item_node.get('ItemChargeAdjustmentList' if refund else 'ItemChargeList')
        if charge_adjustments:
            components = charge_adjustments.ChargeComponent
            if not isinstance(components, list):
                components = [components]
            for line in components:
                component_type = self.get_value(line, 'ChargeType')
                amount = self.get_value(line.ChargeAmount, 'CurrencyAmount', expected_type=float)
                if not tools.float_is_zero(amount, precision_digits=2):
                    if component_type not in at.PRICE_COMPONENTS:
                        raise exceptions.ValidationError(
                            _('Unidentified price component - {}. Order ID').format(component_type))
                    base_values[component_type] += amount

        if not tools.float_is_zero(base_values[at.MAIN_COMPONENT_NAME], precision_digits=2):
            ext_product_code = self.get_value(item_node, 'OrderAdjustmentItemId' if refund else 'OrderItemId')

            asin_code = item_to_asin[ext_product_code]
            vals = {
                'ext_line_name': at.MAIN_COMPONENT_NAME,
                'ext_product_code': ext_product_code,
                'asin_product_code': asin_code,
                'sku_product_code': self.get_value(item_node, 'SellerSKU'),
                'quantity': self.get_value(item_node, 'QuantityShipped', expected_type=float),
                'amount_tax': base_values[at.MAIN_COMPONENT_TAX_NAME],
                'line_amount': base_values[at.MAIN_COMPONENT_NAME],
                'line_type': 'principal',
            }
            order_lines.append((0, 0, vals))

        # Add spec shipping line
        if not tools.float_is_zero(base_values[at.SHIPPING_CHARGE_NAME], precision_digits=2):
            add_spec_line(
                order_lines, at.SHIPPING_COMPONENT_NAME, 'shipping',
                base_values[at.SHIPPING_CHARGE_NAME],
                base_values[at.SHIPPING_COMPONENT_TAX_NAME])

        # Add spec gift-wrap line
        if not tools.float_is_zero(base_values[at.GIFT_COMPONENT_NAME], precision_digits=2):
            add_spec_line(
                order_lines, at.GIFT_COMPONENT_NAME, 'gift_wraps',
                base_values[at.GIFT_COMPONENT_NAME],
                base_values[at.GIFT_COMPONENT_TAX_NAME])

        # Check for any fee lines or adjustments
        fee_adjustments = item_node.get('ItemFeeAdjustmentList' if refund else 'ItemFeeList')
        if fee_adjustments:
            components = fee_adjustments.FeeComponent
            if not isinstance(components, list):
                components = [components]
            for line in components:
                amount = self.get_value(line.FeeAmount, 'CurrencyAmount', expected_type=float)
                if not tools.float_is_zero(amount, precision_digits=2):
                    add_spec_line(order_lines, self.get_value(
                        line, 'FeeType'), 'fees', amount)

        # Check for any promotion lines that act as discounts
        promotion_adjustments = item_node.get('PromotionAdjustmentList' if refund else 'PromotionList')
        if promotion_adjustments:
            components = promotion_adjustments.Promotion
            if not isinstance(components, list):
                components = [components]
            promotion_components = {}
            for line in components:
                amount = self.get_value(line.PromotionAmount, 'CurrencyAmount', expected_type=float)
                if not tools.float_is_zero(amount, precision_digits=2):
                    # Components have taxes which we do not want to import
                    # So we map by name and take the higher value
                    promotion_id = self.get_value(line, 'PromotionId')
                    if promotion_id not in promotion_components:
                        promotion_components[promotion_id] = amount
                    else:
                        # Compare ABS'ed amounts
                        if tools.float_compare(
                                abs(amount), abs(promotion_components[promotion_id]), precision_digits=2) > 0:
                            promotion_components[promotion_id] = amount

            # After we decided which value to use, loop again by having
            # Unique promotion IDs and append them  to order lines
            for promotion, line_amount in iteritems(promotion_components):
                add_spec_line(order_lines, promotion, 'promotion', line_amount)

    @api.model
    def init_api_fetch_product_categories(self):
        """
        ! METHOD NOT USED AT THE MOMENT !
        Fetch products and product categories from order API, because
        actual Amazon product api does not work as expected...
        Proceed to create them as amazon product/category objects
        :return: list of product categories with products
        """
        dummy = self.env['amazon.region']
        product_api = self.get_api(dummy, api_type='products')
        order_api = self.get_api(dummy, api_type='orders')

        # Init sync date for product categories is always 1 months ago
        temp_date_dt = datetime.utcnow()
        sync_date_dt = temp_date_dt - relativedelta(months=1)

        fetched_orders = []

        # Order API is limited to 100 orders per request so we fetch them day by day, from sync date till today
        while temp_date_dt > sync_date_dt:
            temp_date = temp_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            orders = self.api_throttle_handler(
                order_api, method='orders',
                extra_args={'marketplaceids': at.MARKETPLACE_IDS, 'created_after': temp_date}
            )
            if orders:
                # Try parsing orders from the received API response
                # if the matched structure does not exist, raise an error
                try:
                    order_list_resp = orders.parsed.Orders.Order
                except (AttributeError, KeyError):
                    raise exceptions.ValidationError(_('Amazon order API returned malformed query'))

                if not isinstance(order_list_resp, list):
                    order_list_resp = [order_list_resp]
                # Several product ID's are used throughout the API...
                # So we have to fetch one using another one and map it

                for order_data in order_list_resp:
                    # Get order ID from fetched data, if it does not exist, raise an error
                    order_id = self.get_value(order_data, 'AmazonOrderId')
                    if not order_id or order_id in fetched_orders or self.env['amazon.order'].search_count(
                            [('order_id', '=', order_id)]):
                        continue
                    fetched_orders.append(order_id)

                    # Use different API call to fetch ASIN's, different product ID.
                    order_item_resp = self.api_throttle_handler(
                        order_api, method='order_items', extra_args={'amazon_order_id': order_id})

                    try:
                        order_items_data = order_item_resp.parsed.OrderItems.OrderItem
                    except (AttributeError, KeyError):
                        raise exceptions.ValidationError(_('Amazon order line API returned malformed query'))

                    if not isinstance(order_items_data, list):
                        order_items_data = [order_items_data]
                    for item_data in order_items_data:
                        item_asin = self.get_value(item_data, 'ASIN')
                        if self.env['amazon.product'].search_count([('asin_product_code', '=', item_asin)]):
                            continue
                        self.fetch_create_amazon_product(product_api, order_data, item_data)

            temp_date_dt -= relativedelta(days=1)

    @api.model
    def fetch_create_amazon_product(self, product_api, order_data, item_data):
        """
        Fetch product/categories data from API and create corresponding Amazon objects
        :param product_api: product_api mws object
        :param order_data: order data from other endpoint
        :param item_data: item data from other endpoint
        :return: None
        """

        # Get needed values
        marketplace_code = self.get_value(order_data, 'MarketplaceId')
        marketplace_name = self.get_value(order_data, 'SalesChannel')
        item_order_id = self.get_value(item_data, 'OrderItemId')
        item_asin = self.get_value(item_data, 'ASIN')

        # Get products from the API
        products_resp = self.api_throttle_handler(
            product_api, method='products', extra_args={
                'marketplaceid': marketplace_code,
                'type_': 'ASIN',
                'ids': [item_asin]
            }
        )
        # Get products categories from API
        category_resp = self.api_throttle_handler(
            product_api, method='categories', extra_args={
                'marketplaceid': marketplace_code,
                'asin': item_asin
            }
        )
        # If category set is empty we skip it
        if not category_resp.parsed:
            return
        try:
            category_data = category_resp.parsed.Self
        except (AttributeError, KeyError):
            raise exceptions.ValidationError(_('Amazon product API returned malformed query'))

        if isinstance(category_data, list):
            category_data = category_data[-1]

        # Get lowest-level parent category of the object
        parent_category = category_data
        while hasattr(parent_category, 'Parent'):
            parent_category = parent_category.Parent

        try:
            item_attributes = products_resp.parsed.Products.Product.AttributeSets.ItemAttributes
        except (AttributeError, KeyError):
            raise exceptions.ValidationError(_('Amazon product API returned malformed query'))

        category_name = self.get_value(parent_category, 'ProductCategoryName')
        group_from_product = self.get_value(item_attributes, 'ProductGroup')

        ext_category_id = self.get_value(parent_category, 'ProductCategoryId')
        amazon_category = self.env['amazon.product.category'].search(
            [('external_id', '=', ext_category_id)])

        if not amazon_category:
            amazon_category = self.env['amazon.product.category'].create({
                'name': '{} / {}'.format(marketplace_name, category_name),
                'group_from_product': group_from_product,
                'marketplace_code': marketplace_code,
                'external_id': ext_category_id,
            })

        self.env['amazon.product'].create({
            'brand': self.get_value(item_attributes, 'Brand'),
            'model': self.get_value(item_attributes, 'Model'),
            'product_group': group_from_product,
            'product_name': self.get_value(item_attributes, 'Title'),
            'asin_product_code': item_asin,
            'ext_product_code': item_order_id,
            'amazon_category_id': amazon_category.id
        })

    # Misc methods // -------------------------------------------------------------------------------------------------

    @api.model
    def get_sync_date(self):
        """
        Get API synchronization date. If it does not exist, use accounting threshold.
        If no date is found, raise an exception
        :return: sync date (str), initial_fetch True/False (if threshold date is used, initial fetch is True)
        """
        company = self.sudo().env.user.company_id
        sync_date = company.amazon_api_sync_date
        initial_fetch = False
        if not sync_date:
            sync_date = company.amazon_accounting_threshold_date
            initial_fetch = True
        if not sync_date:
            raise exceptions.UserError(_('Nesukonfigūruota apskaitos pradžios data!'))
        return sync_date, initial_fetch

    @api.model
    def set_sync_date(self):
        """
        Set Amazon accounting sync date
        :return: None
        """
        self.sudo().env.user.company_id.write(
            {'amazon_api_sync_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})

    @api.model
    def get_value(self, dict_node, key, expected_type=None):
        """
        Fetch value from passed Amazon pseudo-dict format
        :param dict_node: Amazon dict object
        :param key: field to fetch
        :param expected_type: expected field type
        :return: fetched value (str, float)
        """
        value = 0.0 if expected_type is float else str()
        try:
            value = dict_node[key]['value']
            if expected_type is float:
                try:
                    value = float(value)
                except (ValueError, AttributeError):
                    pass
        except (AttributeError, KeyError, TypeError):
            pass
        return value

    @api.model
    def parse_date_value(self, date_str, return_dt=False):
        """
        Parse and format date value to the DEFAULT DATETIME FORMAT
        :param date_str: passed date
        :param return_dt: If marked as True, return datetime object
        :return: formatted date (str) / datetime object
        """
        # Return old datetime if return_dt is specified else empty string
        parsed_date = datetime(2000, 01, 01) if return_dt else str()
        if isinstance(date_str, basestring):
            # Always replace timezone to UTC
            parsed_date = parse(date_str).replace(tzinfo=pytz.UTC)
            if not return_dt:
                parsed_date = parsed_date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return parsed_date

    @api.model
    def parse_bool_value(self, value):
        """
        Check whether passed value can be converted to pythonic boolean, if not, return False
        otherwise converted value
        :param value: Value to be tested for boolean
        :return: True / False
        """
        if not isinstance(value, bool):
            if isinstance(value, int) and value in [1, 0]:
                return bool(value)
            if isinstance(value, basestring):
                return True if value.lower() in ['true', '1'] else False
            return False
        return value
