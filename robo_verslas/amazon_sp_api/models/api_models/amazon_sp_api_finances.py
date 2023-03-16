# -*- coding: utf-8 -*-
from odoo import models, api


class AmazonSPAPIFinances(models.AbstractModel):
    _name = 'amazon.sp.api.finances'
    _inherit = 'amazon.sp.api.base'
    _description = 'Abstract model that contains Amazon financial events API methods'

    # API Core --------------------------------------------------------------------------------------------------------

    @api.model
    def get_api_static_action_data(self):
        """
        Updates the base API static data dict with financial events endpoints
        :return: endpoint action data (dict)
        """
        # Call the super to get the action data
        action_data = super(AmazonSPAPIFinances, self).get_api_static_action_data()
        # Update action data with order API data
        order_action_data = {
            'get_order_financial_events': {
                'canonical_url': '/finances/v0/orders/{object_id}/financialEvents',
                'requires_authentication': True,
                'method': 'GET',
            },
        }
        action_data.update(order_action_data)
        return action_data

    # API Data Methods ------------------------------------------------------------------------------------------------

    @api.model
    def api_get_order_financial_events(self, region, order_id):
        """
        Method that is used to fetch financial event information
        for specific order information based on it's ID.
        Result of the API query is then passed to processing methods.
        :return: Processed data and boolean value
        indicating whether all data was fetched (dict)
        """

        # Prepare request data
        base_url = region.region_endpoint
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_order_financial_events',
            'manual_action': True,
            'extra_data': {'base_url': base_url, 'region': region, 'object_id': order_id}
        }, data_type='Order financial events')

        # Process fetched financial events for current order
        fetched_data = {}
        if call_result['fetched_data']:
            preprocessed_data = call_result['fetched_data'].pop()
            fetched_data = preprocessed_data['FinancialEvents']

        return {
            'period_fetched': call_result['period_fetched'],
            'fetched_data': fetched_data,
        }
