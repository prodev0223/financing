# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import models, api, tools, _
from datetime import datetime


class AmazonSPAPIInventory(models.AbstractModel):
    _name = 'amazon.sp.api.inventory'
    _inherit = 'amazon.sp.api.base'
    _description = _('Abstract model that contains Amazon inventory API methods')

    # API Core --------------------------------------------------------------------------------------------------------

    @api.model
    def get_api_static_action_data(self):
        """
        Updates the base API static data dict with inventory endpoints
        :return: endpoint action data (dict)
        """
        # Call the super to get the action data
        action_data = super(AmazonSPAPIInventory, self).get_api_static_action_data()
        # Update action data with order API data
        order_action_data = {
            'get_inventory_summaries': {
                'canonical_url': '/fba/inventory/v1/summaries',
                'requires_authentication': True,
                'method': 'GET',
            },
        }
        action_data.update(order_action_data)
        return action_data

    # API Data Methods ------------------------------------------------------------------------------------------------

    @api.model
    def api_get_inventory_summaries(self, marketplace, date_from):
        """
        Method that is used to fetch financial event information
        for specific order information based on it's ID.
        Result of the API query is then passed to processing methods.
        :param marketplace: Marketplace of desired inventory summaries
        :param date_from: Inventory summary period start date
        :return: Processed data, processed data period end date and boolean value
        indicating whether all data was fetched (dict)
        """

        region = marketplace.region_id
        # Prepare request data
        base_request_query = {
            'granularityType': 'Marketplace',
            'granularityId': marketplace.code,
            'marketplaceIds': [marketplace.code],
            'startDateTime': self.convert_date_iso_format(date_from),
        }
        base_url = region.region_endpoint
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_inventory_summaries',
            'manual_action': True,
            'extra_data': {'base_url': base_url, 'region': region, }

        }, data_type='Inventory summaries', base_request_query=base_request_query)

        # Query does not return period end, so we assume that
        # 10 seconds is sufficient error covering value
        period_end = datetime.utcnow() - relativedelta(seconds=10)

        # Process the data
        processed_data = []
        if call_result['period_fetched']:
            preprocessed_data = [
                summary for payload in call_result['fetched_data'] for summary in payload['inventorySummaries']
            ]
            processed_data = self.process_fetched_inventory_summaries(
                preprocessed_data, period_start=date_from,
                period_end=period_end, marketplace=marketplace,
            )
        return {
            'period_fetched': call_result['period_fetched'],
            'processed_data': processed_data,
            'period_end': period_end,
        }

    # Processing Methods ----------------------------------------------------------------------------------------------

    @api.model
    def process_fetched_inventory_summaries(self, fetched_inventory_data, period_start, period_end, marketplace):
        """
        Processes fetched data and prepares it for Amazon inventory object creation
        :param fetched_inventory_data: API fetched inventory summary data
        :param period_start: Inventory period start date (str)
        :param period_end: Inventory period end data (str)
        :param marketplace: Amazon SP marketplace (record)
        :return: Processed inventory data (list)
        """
        # Needed objects
        AmazonSPAPIItems = self.env['amazon.sp.api.catalog.items'].sudo()
        AmazonSPProduct = self.env['amazon.sp.product'].sudo()

        grouped_inventory_data = {}
        for inventory_summary in fetched_inventory_data:
            summary_details = inventory_summary.get('inventoryDetails', {})
            # Check if unfulfillable quantity block exists, and skip if it does not
            unfulfillable_quantity_block = summary_details.get('unfulfillableQuantity', {})
            if not unfulfillable_quantity_block:
                continue
            # If total unfulfillable quantity is zero - we skip
            total_unfulfillable = float(
                unfulfillable_quantity_block.pop('totalUnfulfillableQuantity', 0.0)
            )
            if tools.float_is_zero(total_unfulfillable, precision_digits=2):
                continue

            # Get the ASIN of the item
            asin_product_code = inventory_summary.get('asin', str())
            # Check if the product exists in the system, if it does not - fetch it
            if not AmazonSPProduct.search_count([('asin_product_code', '=', asin_product_code)]):
                # Generate artificial external code
                AmazonSPAPIItems.fetch_create_amazon_product(
                    product_codes={'asin_product_code': asin_product_code, 'ext_product_code': False},
                    marketplace=marketplace
                )
            # Group the data by inventory reason
            for inventory_reason, quantity in unfulfillable_quantity_block.items():
                # Set default inventory reason and group data by inventory reason
                grouped_inventory_data.setdefault(inventory_reason, {})
                grouped_inventory_data[inventory_reason].update({
                    asin_product_code: quantity,
                })
        # Build processed data structure that is ready to be passed to inventory create methods
        processed_inventory_data = []
        if grouped_inventory_data:
            for inventory_reason, product_data in grouped_inventory_data.items():
                inventory_lines = []
                inventory_values = {
                    'period_start_date': period_start,
                    'period_end_date': period_end,
                    'marketplace_id': marketplace.id,
                    'write_off_reason': inventory_reason,
                    'amazon_inventory_line_ids': inventory_lines,
                }
                # Prepare line values
                for asin_product_code, quantity in product_data.items():
                    line_values = {'asin_product_code': asin_product_code, 'write_off_quantity': quantity}
                    inventory_lines.append((0, 0, line_values))

                # Add inventory data to processed list
                processed_inventory_data.append(inventory_values)
        return processed_inventory_data

    # Cron jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_fetch_inventory_summaries(self):
        """
        Cron job that fetches and creates inventory summaries
        at the start of every month.
        :return: None
        """

        # Only fetch inventory summaries if quantitative integration is set
        configuration = self.get_configuration()
        if not configuration or configuration.integration_type != 'qty':
            return

        # Get inventory fetch day
        # Not a field in SP configuration, since it's not meant to be modified by user
        try:
            inventory_fetch_day = int(self.sudo().env['ir.config_parameter'].get_param(
                'amazon_qty_integration_inventory_fetch_day'))
        except (ValueError, TypeError):
            inventory_fetch_day = 1

        # Check today's day, and whether inventories should be fetched
        day_today = datetime.utcnow().day
        if inventory_fetch_day != day_today:
            return

        # Needed objects
        AmazonSPInventoryAct = self.env['amazon.sp.inventory.act'].sudo()
        AmazonSPMarketplace = self.env['amazon.sp.marketplace'].sudo()

        threshold_date = configuration.accounting_threshold_date
        # TODO: Inventory summaries are only available in US for now (2022 will allow all regions)
        us_region = self.env.ref('amazon_sp_api.amazon_sp_region_na')
        codes = us_region.mapped('marketplace_ids.code')
        marketplaces = AmazonSPMarketplace.search(
            [('region_id.api_state', '=', 'working'), ('activated', '=', True), ('code', 'in', codes)]
        )
        for marketplace in marketplaces:
            sync_date = marketplace.inventory_api_sync_date or threshold_date
            # Fetch the inventories for the marketplace
            api_get_inventory_summaries_response = self.api_get_inventory_summaries(
                marketplace=marketplace, date_from=sync_date,
            )
            # Only execute the actions if period was fetched
            # otherwise sync date is not updated.
            if api_get_inventory_summaries_response['period_fetched']:
                # Loop through inventories and create them
                for inventory_values in api_get_inventory_summaries_response['processed_data']:
                    AmazonSPInventoryAct.create(inventory_values)
                    if not tools.config.get('test_enable'):
                        self.env.cr.commit()
                # Get the period end date and save it to marketplace
                period_end_date = api_get_inventory_summaries_response['period_end']
                marketplace.write({'inventory_api_sync_date': period_end_date})

    @api.model
    def cron_create_from_inventory_summaries(self):
        """
        Cron job that fetches and creates inventory summaries
        at the start of every month.
        :return: None
        """
        # Only create inventory summaries if quantitative integration is set
        configuration = self.get_configuration()
        if not configuration or configuration.integration_type != 'qty':
            return

        AmazonSPInventoryAct = self.env['amazon.sp.inventory.act'].sudo()
        inventories_to_create = AmazonSPInventoryAct.search(
            [('state', 'in', ['imported', 'failed'])]
        )
        inventories_to_create.create_inventory_write_off_prep()
