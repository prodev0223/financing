# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _


class AmazonSPAPICatalogItems(models.AbstractModel):
    _name = 'amazon.sp.api.catalog.items'
    _inherit = 'amazon.sp.api.base'
    _description = _('Model that contains Amazon Catalog Items model related API methods')

    # API Core --------------------------------------------------------------------------------------------------------

    @api.model
    def get_api_static_action_data(self):
        """
        Updates the base API static data dict with items endpoints
        :return: endpoint action data (dict)
        """
        # Call the super to get the action data
        action_data = super(AmazonSPAPICatalogItems, self).get_api_static_action_data()
        # Update action data with order API data
        order_action_data = {
            'get_product_by_asin': {
                'canonical_url': '/catalog/v0/items/{object_id}',
                'requires_authentication': True,
                'method': 'GET',
            },
            'get_categories_by_asin': {
                'canonical_url': '/catalog/v0/categories',
                'requires_authentication': True,
                'method': 'GET',
            },
        }
        action_data.update(order_action_data)
        return action_data

    # API data methods ------------------------------------------------------------------------------------------------

    @api.model
    def api_get_product(self, marketplace, product_codes):
        """
        Fetch products data from API and create corresponding Amazon objects
        :param marketplace: Marketplace that product belongs to (record)
        :param product_codes: Product ASIN identifier and external_code (dict)
        :return: Amazon SP product (record)
        """
        # Get the region and base URL
        region = marketplace.region_id
        base_url = region.region_endpoint
        # Build base request query
        base_request_query = {
            'MarketplaceId': marketplace.code,
        }
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_product_by_asin',
            'manual_action': True,
            'extra_data': {
                'base_url': base_url, 'region': region,
                'object_id': product_codes['asin_product_code'],
            }
        }, data_type='Product information', base_request_query=base_request_query)

        AmazonSPProduct = self.env['amazon.sp.product']
        # Check if whole period was fetched
        if call_result['period_fetched']:
            # Gather fetched data and process it
            preprocessed_data = call_result['fetched_data'].pop()
            AmazonSPProduct = self.process_product_data(
                marketplace, preprocessed_data, preprocess_data={'product_codes': product_codes}
            )
        return AmazonSPProduct

    @api.model
    def api_get_product_categories(self, marketplace, asin_product_code):
        """
        Fetch product category data from API and create corresponding Amazon
        objects if they don't yet exist in the system.
        Category record(s) are returned despite the fact if anything was created
        :param marketplace: Marketplace that product belongs to (record)
        :param asin_product_code: Related product's ASIN (str)
        :return: Amazon SP category (recordset)
        """

        region = marketplace.region_id
        base_url = region.region_endpoint
        # Build base request query
        base_request_query = {
            'MarketplaceId': marketplace.code,
            'ASIN': asin_product_code,
        }
        call_result = self.call_api_continuation_key_wrapper(call_data={
            'action': 'get_categories_by_asin',
            'manual_action': True,
            'extra_data': {
                'base_url': base_url, 'region': region,
            }
        }, data_type='Product category information', base_request_query=base_request_query)

        AmazonSPProductCategory = self.env['amazon.sp.product.category']
        # Process fetched orders for current marketplace
        if call_result['fetched_data']:
            # Pre-process data structure
            fetched_data_list = [category for payload in call_result['fetched_data'] for category in payload]
            AmazonSPProductCategory |= self.process_fetched_categories(marketplace, fetched_data_list)
        return AmazonSPProductCategory

    # Processing methods ----------------------------------------------------------------------------------------------

    @api.model
    def process_fetched_categories(self, marketplace, fetched_data_list):
        """
        Processes fetched Amazon categories for specific ASIN, searches for
        bottom-most parent category, creates systemic record and returns the data.
        :param marketplace: Marketplace that category belongs to (record)
        :param fetched_data_list: Fetched category data (list)
        :return: Amazon SP category (record)
        """
        AmazonSPProductCategory = self.env['amazon.sp.product.category'].sudo()
        # Take the last category of the list
        category_data = fetched_data_list.pop()

        # Get lowest-level parent category of the object
        parent_category = category_data
        while parent_category.get('parent'):
            parent_category = parent_category.get('parent')

        # Get category_data
        category_name = parent_category.get('ProductCategoryName')
        ext_category_id = parent_category.get('ProductCategoryId')
        # Check if record already exists and if it doesn't - create it
        amazon_category = AmazonSPProductCategory.search([('external_id', '=', ext_category_id)])
        if not amazon_category:
            amazon_category = AmazonSPProductCategory.create({
                'name': '{} / {}'.format(marketplace.name, category_name),
                'marketplace_code': marketplace.code,
                'external_id': ext_category_id,
            })
        return amazon_category

    @api.model
    def process_product_data(self, marketplace, product_data, preprocess_data):
        """
        Method that is used to process product data and create corresponding record.
        :param marketplace: Marketplace of the fetched product (record)
        :param product_data: API fetched product data (dict)
        :param preprocess_data: Static passed product data (dict)
        :return: Amazon SP product (record)
        """
        AmazonSPProduct = self.env['amazon.sp.product'].sudo()
        p_codes = preprocess_data['product_codes']

        attribute_sets = product_data['AttributeSets']
        if not attribute_sets:
            raise exceptions.ValidationError(
                _('Amazon SP-API [{}]. Product with ASIN [{}] does not have attribute sets').format(
                    marketplace.code, p_codes['asin_product_code'])
            )
        # Take the first attribute Set
        attribute_set = attribute_sets[0]
        # Update preprocess data with group name that came from the product endpoint.
        # This value differs from the one that comes in category endpoint, but
        # it matches throughout the products that contain the same category,
        # thus we save it as a separate field just in case this value is needed.
        product_group = attribute_set['ProductGroup']
        product_group_type = attribute_set.get('ProductTypeName')

        # Get the categories for current product
        amazon_category = self.api_get_product_categories(marketplace, p_codes['asin_product_code'])
        if not amazon_category:
            raise exceptions.ValidationError(
                _('Amazon SP-API [{}]. Failed to create product category with ASIN [{}]').format(
                    marketplace.code, p_codes['asin_product_code'])
            )
        # Fetch category data
        amazon_product = AmazonSPProduct.create({
            'product_group': product_group,
            'product_group_type': product_group_type,
            'product_name': attribute_set.get('Title', 'Product'),
            'asin_product_code': p_codes['asin_product_code'],
            'ext_product_code': p_codes['ext_product_code'],
            'amazon_category_id': amazon_category.id
        })
        return amazon_product

    # Creation methods ------------------------------------------------------------------------------------------------

    @api.model
    def fetch_create_amazon_product(self, product_codes, marketplace=None, marketplace_code=None):
        """
        Method that is used to fetch product data from Amazon API
        and create corresponding Amazon/Systemic objects.
        :param product_codes: product ASIN code and external code (dict)
        :param marketplace: Optional parameter to pass marketplace (record/None)
        :param marketplace_code: Optional parameter to pass marketplace code (str/None)
        :return: None
        """
        if marketplace is None and marketplace_code is None:
            # Detail in the message is enough, this should
            # never occur outside of the testing phase
            raise exceptions.ValidationError(_('Invalid input'))
        # Get the marketplace by code if record is not passed
        if marketplace is None:
            marketplace = self.env['amazon.sp.marketplace'].search([('code', '=', marketplace_code)])
        # Create amazon product and then create systemic template
        amazon_product = self.api_get_product(marketplace=marketplace, product_codes=product_codes)
        amazon_product.create_product_template_prep()
