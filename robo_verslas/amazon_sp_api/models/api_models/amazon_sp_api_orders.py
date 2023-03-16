# -*- coding: utf-8 -*-
from odoo import models, api, tools, exceptions, _
from odoo.addons.queue_job.job import job, identity_exact
from dateutil.relativedelta import relativedelta
from ... import amazon_sp_api_tools as at
from dateutil.parser import parse
from datetime import datetime
from six import iteritems
import pytz


class AmazonSPAPIOrders(models.AbstractModel):
    _name = 'amazon.sp.api.orders'
    _inherit = 'amazon.sp.api.base'
    _description = _('Model that contains Amazon order API methods')

    # API Core --------------------------------------------------------------------------------------------------------

    @api.model
    def get_api_static_action_data(self):
        """
        Updates the base API static data dict with order endpoints
        :return: endpoint action data (dict)
        """
        # Call the super to get the action data
        action_data = super(AmazonSPAPIOrders, self).get_api_static_action_data()
        # Update action data with order API data
        order_action_data = {
            'get_order': {
                'canonical_url': '/orders/v0/orders/{object_id}',
                'requires_authentication': True,
                'method': 'GET',
            },
            'get_order_items': {
                'canonical_url': '/orders/v0/orders/{object_id}/orderItems',
                'requires_authentication': True,
                'method': 'GET',
            },
            'get_orders': {
                'canonical_url': '/orders/v0/orders',
                'requires_authentication': True,
                'method': 'GET',
            },
        }
        action_data.update(order_action_data)
        return action_data

    # API Data Methods ------------------------------------------------------------------------------------------------

    @api.model
    def api_get_orders(self, region, date_from, marketplaces=None, date_to=None, intermediate_creation=False):
        """
        Method that is used to fetch orders for specific marketplace
        or marketplace group for specific time period.
        Result of the API query is then passed to order creation methods.
        :param region: Related Amazon SP region record (record)
        :param date_from: Order period date from
        :param marketplaces: Related marketplaces that orders correspond to,
        if not passed, all of the active region marketplaces are used.
        :param date_to: Order period date to, if not passed, current date is used
        :param intermediate_creation: Indicates whether Amazon order records
        should be created after the whole batch, or inside of the fetch loop (bool)
        :return: Processed data and boolean value
        indicating whether all data was fetched (dict)
        """

        manual_action = self._context.get('manual_action', True)
        configuration = self.get_configuration()

        # Get marketplaces, either take them from the region or get filtered set
        marketplaces = region.marketplace_ids.filtered(
            lambda x: x.activated
        ) if marketplaces is None else marketplaces
        if not marketplaces:
            raise exceptions.ValidationError(
                _('Amazon SP-API Orders: No active marketplaces passed')
            )

        # Get base request URL from the region
        base_url = region.region_endpoint
        base_request_query = {
            'LastUpdatedAfter': self.convert_date_iso_format(date_from),
            'OrderStatuses': ['Shipped'],
            'MarketplaceIds': marketplaces.mapped('code'),
        }
        # Check what fulfillment channels should be filtered
        order_fc = configuration.order_fulfillment_channels
        if order_fc and order_fc != 'all_channels':
            base_request_query.update({
                'FulfillmentChannels': [order_fc],
            })
        # Check whether date to should be filtered
        if date_to:
            base_request_query.update({'LastUpdatedBefore': self.convert_date_iso_format(date_to), })

        # Call API endpoint with a wrapper
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_orders',
            'manual_action': manual_action,
            'extra_data': {'base_url': base_url, 'region': region}
        }, data_type='Orders', base_request_query=base_request_query)

        processed_data = []
        # Check whether no partial calls failed
        period_fetched = call_result['period_fetched']
        # Process fetched orders for current marketplace
        if call_result['fetched_data']:
            # Pre-process data structure
            preprocessed_data = [
                order for payload in call_result['fetched_data'] for order in payload['Orders']
            ]
            # Process the data
            processed_data, all_lines_fetched = self.process_fetched_orders(
                region, preprocessed_data, intermediate_creation
            )
            # Update the period fetched flag - period is only fetched if no partial order calls failed,
            # and no partial line fails (order lines/financial events) were encountered as well
            period_fetched = period_fetched and all_lines_fetched

        return {
            'period_fetched': period_fetched,
            'processed_data': processed_data,
        }

    @api.model
    def api_get_order_lines(self, region, order_id, marketplace_code):
        """
        Method that is used to fetch lines for specific order.
        Endpoint is used to build ASIN to external code mapping
        :return: Processed data and boolean value
        indicating whether all data was fetched (dict)
        """

        manual_action = self._context.get('manual_action', True)
        # Prepare request data
        base_url = region.region_endpoint
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_order_items',
            'manual_action': manual_action,
            'extra_data': {
                'base_url': base_url, 'region': region,
                'object_id': order_id,
            }
        }, data_type='Order Lines')

        period_fetched = call_result['period_fetched']
        # Process fetched order lines only if all of them were fetched
        processed_data = {}
        if period_fetched:
            # Preprocess the structure and process the data
            preprocessed_data = [
                line for payload in call_result['fetched_data'] for line in payload['OrderItems']
            ]
            processed_data = self.process_order_items(preprocessed_data, marketplace_code)

        return {
            'period_fetched': period_fetched,
            'processed_data': processed_data,
        }

    @api.model
    def api_get_order(self, region, order_id):
        """
        Method that is used to fetch specific order information based on it's ID.
        Result of the API query is then passed to order creation methods.
        :return: Processed data and boolean value
        indicating whether all data was fetched (dict)
        """

        manual_action = self._context.get('manual_action', True)
        # Call API endpoint with a wrapper
        base_url = region.region_endpoint
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_order',
            'manual_action': manual_action,
            'extra_data': {'base_url': base_url, 'region': region, 'object_id': order_id}
        }, data_type='Order')

        processed_data = []
        # Check whether no partial calls failed
        period_fetched = call_result['period_fetched']
        # Process fetched order data
        if call_result['fetched_data']:
            processed_data, all_lines_fetched = self.process_fetched_orders(region, call_result['fetched_data'])
            # Update the period fetched flag - period is only fetched if no partial order calls failed,
            # and no partial line fails (order lines/financial events) were encountered as well
            period_fetched = period_fetched and all_lines_fetched

        return {
            'period_fetched': period_fetched,
            'processed_data': processed_data,
        }

    # Processing Methods ----------------------------------------------------------------------------------------------

    @api.model
    def process_fetched_orders(self, region, fetched_order_data, intermediate_creation=True):
        """
        Processes fetched order data and prepares it for creation.
        If not all order lines are fetched order is created without
        any lines and is later updated by the system.
        :param region: Amazon SP region (record)
        :param fetched_order_data: API fetched order data (list)
        :param intermediate_creation: Indicates whether Amazon order records
        should be created after the whole batch, or inside of the fetch loop (bool)
        :return: Processed order data (list),
        value indicating whether all lines/events for current order period were fetched (bool)
        """

        def parse_date(date):
            """Parse Amazon date and convert to datetime string"""
            return parse(date).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT) if date else str()

        total_order_data = []
        # Get the configuration record
        configuration = self.get_configuration()
        if not configuration:
            return total_order_data

        # Get the accounting threshold date
        threshold_date_dt = datetime.strptime(
            configuration.accounting_threshold_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        threshold_date_dt = pytz.utc.localize(threshold_date_dt)

        # Value that indicates whether all intermediate queries for order lines
        # were completed successfully. If at least one line batch of any one order
        # was not successful, this flag is set to false, and sync date is not updated.
        all_lines_fetched = True
        AmazonSPOrder = self.env['amazon.sp.order']
        AmazonSPAPIFinances = self.env['amazon.sp.api.finances']
        for o_data in fetched_order_data:
            # Get order ID and check for duplicates
            ext_order_id = o_data['AmazonOrderId']

            # Get order total amounts and marketplace code
            order_total = o_data.get('OrderTotal', {})
            control_amount = float(order_total.get('Amount', 0.0))
            currency_code = order_total.get('CurrencyCode', str())
            marketplace_code = o_data['MarketplaceId']

            # Get origin/destination country data
            origin_country = o_data.get('DefaultShipFromLocationAddress', {})
            origin_country_code = origin_country.get('CountryCode')
            destination_country = o_data.get('ShippingAddress', {})
            destination_country_code = destination_country.get('CountryCode')

            order_vals = {
                'ext_order_id': ext_order_id,
                'seller_order_id': o_data.get('SellerOrderId', str()),
                'external_state': o_data['OrderStatus'],
                'fulfillment_channel': o_data.get('FulfillmentChannel', str()),
                'control_amount': control_amount,
                'currency_code': currency_code,
                'number_of_items_unshipped': o_data.get('NumberOfItemsUnshipped', 0),
                'marketplace_code': marketplace_code,
                'order_type': o_data.get('OrderType', 'StandardOrder'),
                'purchase_date': parse_date(o_data['PurchaseDate']),
                'earliest_ship_date': parse_date(o_data.get('EarliestShipDate', str())),
                'latest_ship_date': parse_date(o_data.get('LatestShipDate', str())),
                'earliest_delivery_date': parse_date(o_data.get('EarliestDeliveryDate', str())),
                'latest_delivery_date': parse_date(o_data.get('LatestDeliveryDate', str())),
                'ext_replacement_order_id': o_data.get('ReplacedOrderId', str()),
                'origin_country_code': origin_country_code,
                'destination_country_code': destination_country_code,
            }

            # Fetch the order items and build product code to ASIN mapping
            order_line_api_response = self.api_get_order_lines(region, ext_order_id, marketplace_code)
            if not order_line_api_response['period_fetched']:
                # Not all lines were fetched - update the flag and  continue
                all_lines_fetched = False
                continue

            product_mapping_dict = order_line_api_response['processed_data']
            # Fetch financial events for current order
            finances_api_response = AmazonSPAPIFinances.api_get_order_financial_events(region, ext_order_id)
            if not finances_api_response['period_fetched']:
                # Not all financial events were fetched - update the flag and  continue
                all_lines_fetched = False
                continue

            finances_fetched_data = finances_api_response['fetched_data']
            # Get shipment event list and build order lines based on it
            shipment_event_list = finances_fetched_data.get('ShipmentEventList')
            processed_shipment_data = self.process_order_shipment_events(shipment_event_list, product_mapping_dict)
            order_line_data = processed_shipment_data['order_lines']
            related_refund_order_data = []
            if order_line_data:
                latest_shipment_date_dt = processed_shipment_data['latest_shipment_date']
                if latest_shipment_date_dt:
                    latest_ship_date_str = latest_shipment_date_dt.strftime(
                        tools.DEFAULT_SERVER_DATETIME_FORMAT,
                    )
                    order_vals['latest_ship_date'] = latest_ship_date_str

                # Get factual order date
                if configuration.order_date_to_use == 'purchase_date':
                    factual_order_dt = parse(o_data['PurchaseDate'])
                elif configuration.order_date_to_use == 'shipment_date':
                    factual_order_dt = latest_shipment_date_dt
                else:
                    factual_order_dt = max(
                        parse(o_data['PurchaseDate']), latest_shipment_date_dt
                    )
                # When we get factual order date, only after we process the shipment events,
                #  we can check whether order crosses the threshold accounting date or not
                if threshold_date_dt > factual_order_dt:
                    continue
                factual_order_date = factual_order_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                # Get refund event list, process it and check whether current order
                # has any related refunds - create them in this iteration as well
                refund_event_list = finances_fetched_data.get('RefundEventList')
                related_refund_order_data = self.process_order_refund_events(
                    refund_event_list, order_vals, product_mapping_dict, threshold_date_dt
                )

                # Update order values with line data
                order_vals.update({
                    'amazon_order_line_ids': order_line_data,
                    'factual_order_date': factual_order_date,
                })
            else:
                order_vals.update({'invoiced_externally': True})

            order_data = related_refund_order_data
            # Refunds are always fetched from the order itself, so check to prevent duplicate orders
            # is done here, after all the refunds are gathered
            if not AmazonSPOrder.search_count([('ext_order_id', '=', ext_order_id), ('refund_order', '=', False)]):
                order_data.append(order_vals)

            # Append fetched orders to total order list
            for order_vals in order_data:
                total_order_data.append(order_vals)
                # If intermediate creation flag is passed, create the orders
                # and commit the transaction midway, inside the loop
                if intermediate_creation:
                    AmazonSPOrder.create(order_vals)
                    if not tools.config.get('test_enable'):
                        self.env.cr.commit()
        # Return grouped order data
        return total_order_data, all_lines_fetched

    @api.model
    def process_order_refund_events(self, refund_event_list, order_values, product_mapping, threshold_date_dt):
        """
        Processes order refund event list, and prepares the
        data for corresponding refund order creation.
        :param refund_event_list: API fetched refund events (list)
        :param order_values: Values of the order that is being refunded (dict)
        :param product_mapping: Dict of product code to ASIN mapping (dict)
        :param threshold_date_dt: Accounting threshold date (datetime object)
        :return: Refund order data (list)
        """
        # Needed objects
        AmazonSPOrder = self.env['amazon.sp.order'].sudo()
        refund_order_data = []
        for refund_order in refund_event_list:
            refund_time_dt = parse(refund_order['PostedDate'])
            # We get the correct refund time here, skip it on threshold cross
            if threshold_date_dt > refund_time_dt:
                continue

            factual_order_date = refund_time_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            # If refund with the same parent ID exists on the same time -- Skip it
            if AmazonSPOrder.search_count([
                ('ext_order_id', '=', order_values['ext_order_id']),
                ('factual_order_date', '=', factual_order_date),
                ('refund_order', '=', True),
            ]):
                continue

            # Get all of the refunded lines and prepare the data structure
            refund_lines = []
            item_adjustment_list = refund_order.get('ShipmentItemAdjustmentList')
            for item_adjustment_data in item_adjustment_list:
                refund_lines = self.process_order_event_lines(
                    line_data=item_adjustment_data,
                    product_mapping=product_mapping, refund=True,
                )

            # Prepare refund values and append the data to refund order data
            refund_values = order_values.copy()
            refund_values.update({
                'amazon_order_line_ids': refund_lines, 'refund_order': True,
                'factual_order_date': factual_order_date, 'control_amount': 0.0,
            })
            refund_order_data.append(refund_values)
        return refund_order_data

    @api.model
    def process_order_shipment_events(self, shipment_event_list, product_mapping):
        """
        Processes order shipping event list, and prepares the
        line data for parent fetched order.
        :param shipment_event_list: API fetched shipping events (list)
        :param product_mapping: Dict of product code to ASIN mapping (dict)
        :return: Shipment lines and latest shipment date (dict)
        """

        shipment_dates = []
        order_lines = []
        # Loop through the list and process order lines
        for shipment_event in shipment_event_list:
            shipment_dates.append(parse(shipment_event['PostedDate']))
            # Get shipment lines
            shipment_lines = shipment_event.get('ShipmentItemList', [])
            for shipment_line in shipment_lines:
                order_lines += self.process_order_event_lines(
                    line_data=shipment_line,
                    product_mapping=product_mapping,
                )
        latest_shipment_date = max(shipment_dates) if shipment_dates else False
        # Return latest shipment date and order lines
        return {
            'order_lines': order_lines,
            'latest_shipment_date': latest_shipment_date,
        }

    @api.model
    def process_order_event_lines(self, line_data, product_mapping, refund=False):
        """
        Process fetched order event lines, group and split them by type and prepare
        the structure that corresponds to creation.
        Origin of the processing can be either shipment or refund events.
        :param line_data: Fetched order line data (dict)
        :param product_mapping: product code to ASIN mapping (dict)
        :param refund: signifies whether line is refund or not
        :return: processed lines (list)
        """

        def add_charge_line(line_list, line_name, line_type, line_total, amount_tax=0.0):
            """
            Inner method to add charge lines that are always of 1 quantity and contain
            no product -- (Shipping/Fee/Promotion lines)
            """
            line_values = {
                'name': line_name, 'total_amount_untaxed': line_total,
                'total_tax_amount': amount_tax, 'line_type': line_type,
            }
            line_list.append((0, 0, line_values))

        # Prepare the list of all order lines
        processed_order_lines = []

        # Prepare component name mapping
        base_values = {
            at.MAIN_COMPONENT_NAME: 0.0,
            at.MAIN_COMPONENT_TAX_NAME: 0.0,
            at.SHIPPING_CHARGE_NAME: 0.0,
            at.SHIPPING_COMPONENT_TAX_NAME: 0.0,
            at.GIFT_COMPONENT_NAME: 0.0,
            at.GIFT_COMPONENT_TAX_NAME: 0.0
        }

        # Check for main line components, split amounts based on whether component is tax or not
        ca_key = 'ItemChargeAdjustmentList' if refund else 'ItemChargeList'
        item_charge_list = line_data.get(ca_key, [])
        for item_charge in item_charge_list:
            # Get component type and amounts
            component_type = item_charge.get('ChargeType', str())
            amount_block = item_charge.get('ChargeAmount', {})
            charge_amount = float(amount_block.get('CurrencyAmount', 0.0))
            if not tools.float_is_zero(charge_amount, precision_digits=2):
                if component_type not in at.PRICE_COMPONENTS:
                    raise exceptions.ValidationError(
                        _('Amazon SP-API: Unidentified price component - {}').format(component_type))
                # Append the amount to base values
                base_values[component_type] += charge_amount

        # If principal amount was in the main charge list, create a separate line for it
        if not tools.float_is_zero(base_values[at.MAIN_COMPONENT_NAME], precision_digits=2):
            # Get the ASIN from the mapping that was fetched from order line endpoint
            item_key = 'OrderAdjustmentItemId' if refund else 'OrderItemId'
            ext_product_code = line_data.get(item_key, str())
            asin_code = product_mapping[ext_product_code]
            # Prepare order line data
            vals = {
                'name': at.MAIN_COMPONENT_NAME,
                'ext_product_code': ext_product_code,
                'asin_product_code': asin_code,
                'sku_product_code': line_data.get('SellerSKU', str()),
                'quantity': line_data.get('QuantityShipped', 0.0),
                'total_tax_amount': base_values[at.MAIN_COMPONENT_TAX_NAME],
                'total_amount_untaxed': base_values[at.MAIN_COMPONENT_NAME],
                'line_type': 'principal',
            }
            processed_order_lines.append((0, 0, vals))

        # Add shipping lines
        if not tools.float_is_zero(base_values[at.SHIPPING_CHARGE_NAME], precision_digits=2):
            add_charge_line(
                processed_order_lines, at.SHIPPING_COMPONENT_NAME, 'shipping',
                base_values[at.SHIPPING_CHARGE_NAME], base_values[at.SHIPPING_COMPONENT_TAX_NAME],
            )
        # Add gift wrap line
        if not tools.float_is_zero(base_values[at.GIFT_COMPONENT_NAME], precision_digits=2):
            add_charge_line(
                processed_order_lines, at.GIFT_COMPONENT_NAME, 'gift_wraps',
                base_values[at.GIFT_COMPONENT_NAME], base_values[at.GIFT_COMPONENT_TAX_NAME],
            )

        # Check for any fee lines or adjustments
        fa_key = 'ItemFeeAdjustmentList' if refund else 'ItemFeeList'
        fee_list = line_data.get(fa_key, [])
        for fee_data in fee_list:
            # Get fee data and append the line
            amount_block = fee_data.get('FeeAmount', {})
            fee_amount = float(amount_block.get('CurrencyAmount', 0.0))
            fee_type = fee_data.get('FeeType', str())
            # Add the line if fee amount is not zero
            if not tools.float_is_zero(fee_amount, precision_digits=2):
                add_charge_line(processed_order_lines, fee_type, 'fees', fee_amount)

        # Check for any fee lines or adjustments
        withheld_tax_list = line_data.get('ItemTaxWithheldList', [])
        for withheld_tax_data in withheld_tax_list:
            withheld_tax_block = withheld_tax_data.get('TaxesWithheld', [])
            for withheld_tax in withheld_tax_block:
                amount_block = withheld_tax.get('ChargeAmount', {})
                # Get fee data and append the line
                tax_amount = float(amount_block.get('CurrencyAmount', 0.0))
                charge_type = withheld_tax.get('ChargeType', str())
                # Add the line if fee amount is not zero
                if not tools.float_is_zero(tax_amount, precision_digits=2):
                    add_charge_line(processed_order_lines, charge_type, 'withheld_taxes', tax_amount)

        # Check for any promotion lines that act as discounts
        pr_key = 'PromotionAdjustmentList' if refund else 'PromotionList'
        promotion_charge_list = line_data.get(pr_key, [])
        if promotion_charge_list:
            promotion_components = {}
            for promotion_line in promotion_charge_list:
                # Get the amount blocks
                amount_block = promotion_line.get('PromotionAmount', {})
                promo_amount = float(amount_block.get('CurrencyAmount', 0.0))
                if not tools.float_is_zero(promo_amount, precision_digits=2):
                    # Components have taxes which we do not want to import
                    # So we map by name and take the higher value
                    promotion_id = promotion_line.get('PromotionId', str())
                    promotion_components.setdefault(promotion_id, [])
                    promotion_components[promotion_id].append(promo_amount)
                    if len(promotion_components[promotion_id]) > 2:
                        # TODO: Used to check data anomalies, on encounter - build a workaround and remove the raise
                        # Assumption - there should always be no more than two amounts for the same ID,
                        # one is main amount, and the other are it's taxes
                        raise exceptions.ValidationError(
                            _('Amazon SP-API: Got more than two promotion amounts for the same ID')
                        )

            # After we decided which value to use, loop again by having
            # Unique promotion IDs and append them to order lines
            for promotion, line_amounts in iteritems(promotion_components):
                # Get the main promo amount and pop it from the list
                promo_amount = max(line_amounts)
                line_amounts.pop(line_amounts.index(promo_amount))
                # Get the promo tax amount
                promo_tax_amount = min(line_amounts) if line_amounts else 0.0
                add_charge_line(processed_order_lines, promotion, 'promotion', promo_amount, promo_tax_amount)
        return processed_order_lines

    @api.model
    def process_order_items(self, fetched_order_line_data, marketplace_code):
        """
        Processes fetched order lines and prepares ASIN to external item code mapping
        :param marketplace_code: Code of the related marketplace (str)
        :param fetched_order_line_data: Fetched API data (dict)
        :return: order line list (formatted for record creation)
        """

        code_to_asin_mapping = {}
        configuration = self.get_configuration()
        # Needed objects
        AmazonSPProduct = self.env['amazon.sp.product']
        AmazonSPAPIItems = self.env['amazon.sp.api.catalog.items']
        # Loop through fetched data and build the mapping
        for line_data in fetched_order_line_data:
            # Get product ASIN and check whether related Amazon product exists in the system
            # if it does not exist - fetch product's and category data
            asin_product_code = line_data['ASIN']
            ext_product_code = line_data['OrderItemId']
            if configuration.integration_type == 'qty' and not \
                    AmazonSPProduct.search_count([('asin_product_code', '=', asin_product_code)]):
                # Fetch and created related amazon  product
                AmazonSPAPIItems.fetch_create_amazon_product(
                    product_codes={'asin_product_code': asin_product_code, 'ext_product_code': ext_product_code},
                    marketplace_code=marketplace_code
                )
            # Set product code to ASIN mapping
            code_to_asin_mapping.setdefault(ext_product_code, asin_product_code)
            # Ensure that mapping is consistent throughout
            if code_to_asin_mapping[ext_product_code] != asin_product_code:
                raise exceptions.ValidationError(
                    _('Amazon SP-API: Order line API inconsistency between ASIN and product code')
                )
        return code_to_asin_mapping

    # Cron jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_fetch_orders(self):
        """
        Fetches Amazon orders for all activated marketplaces
        that belong to the working region and creates related
        systemic records.
        API sync date is updated after successful period fetch.
        :return: None
        """
        # Check if configuration record exists
        configuration = self.get_configuration()
        if not configuration:
            return

        # Needed objects
        AmazonSPMarketplace = self.env['amazon.sp.marketplace']

        threshold_date = configuration.accounting_threshold_date
        # Get activated marketplaces for each working region
        marketplaces = AmazonSPMarketplace.search(
            [('region_id.api_state', '=', 'working'), ('activated', '=', True)]
        )
        for marketplace in marketplaces:
            marketplace.with_delay(eta=5, channel='root.single_1', identity_key=identity_exact).fetch_orders(threshold_date)

    @api.model
    def cron_create_from_orders(self):
        """
        Create account invoices based on aggregated orders
        :return: None
        """
        configuration = self.get_configuration()
        if not configuration:
            return

        # Set default values
        default_domain = [('state', 'in', ['imported', 'failed'])]
        AmazonSPOrder = self.env['amazon.sp.order']

        # If individual invoice creation is enabled - simply create orders w/o any filtering
        if configuration.create_individual_order_invoices:
            AmazonSPOrder.search(default_domain).invoice_creation_prep()

        # Otherwise, check if current  day is order creation day, and if it is, filter the batches
        # to only include the selected period up to next order creation date
        elif configuration.check_order_creation_date():
            interval = configuration.order_creation_interval
            creation_threshold_dt = datetime.strptime(
                configuration.next_order_creation_date, tools.DEFAULT_SERVER_DATE_FORMAT
            ) + relativedelta(hour=23, minute=59, second=59)

            # Determine date to and from based on the interval
            if interval != 'monthly':
                date_to_dt = creation_threshold_dt - relativedelta(days=1)
                day_count = 1 if interval == 'daily' else 7
                date_from_dt = date_to_dt - relativedelta(days=day_count, hour=0, minute=0, second=0)
            else:
                # On monthly interval we always take previous month's end and start dates
                date_to_dt = creation_threshold_dt - relativedelta(months=1, day=31)
                date_from_dt = date_to_dt - relativedelta(day=1, hour=0, minute=0, second=0)

            # Append calculated dates to filter domain
            date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            default_domain.extend([
                ('factual_order_date', '>=', date_from),
                ('factual_order_date', '<=', date_to),
            ])

            # Search and create the orders
            all_batches_validated = AmazonSPOrder.search(default_domain).invoice_creation_prep()
            # Creation date is only pushed if all of the current batches were validated
            if all_batches_validated:
                configuration.set_order_creation_date()
