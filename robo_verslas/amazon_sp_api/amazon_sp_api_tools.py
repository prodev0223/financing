# -*- coding: utf-8 -*-
from odoo import _

# File that contains static Amazon values/mappings.
# Variables here are not likely to change thus
# config parameters are not used.

# External product name mappings/values
MAIN_COMPONENT_NAME = 'Principal'
MAIN_COMPONENT_TAX_NAME = 'Tax'
SHIPPING_COMPONENT_NAME = 'Shipping'
SHIPPING_CHARGE_NAME = 'ShippingCharge'
SHIPPING_COMPONENT_TAX_NAME = 'ShippingTax'
GIFT_COMPONENT_NAME = 'GiftWrap'
GIFT_COMPONENT_TAX_NAME = 'GiftWrapTax'

PRICE_COMPONENTS = [
    MAIN_COMPONENT_NAME, MAIN_COMPONENT_TAX_NAME, SHIPPING_COMPONENT_NAME,
    SHIPPING_COMPONENT_TAX_NAME, SHIPPING_CHARGE_NAME, GIFT_COMPONENT_NAME, GIFT_COMPONENT_TAX_NAME,
]
CORRESPONDING_TAXES = {
    MAIN_COMPONENT_NAME: MAIN_COMPONENT_TAX_NAME,
    SHIPPING_COMPONENT_NAME: SHIPPING_COMPONENT_TAX_NAME,
    GIFT_COMPONENT_NAME: GIFT_COMPONENT_TAX_NAME
}

# API request response code values
GENERAL_API_RESPONSE_MAPPING = {
    200: _('Request has succeeded.'),
    201: _('Request has succeeded, new resource has been created.'),
    422: _('The request cannot be fulfilled due to bad syntax.'),
    401: _('Invalid Amazon keys.'),
    403: _('Access to the selected resource is forbidden.'),
    404: _('Specified object was not found in Amazon system.'),
    429: _('You have sent too many requests in a given amount of time.'),
    500: _('Error on Amazon server side, try again later.'),
}
THROTTLED_ENDPOINT_CODE = 429
EXTERNAL_FAILURE_CODE = 500

# Signature static values
SIGNED_HEADER_VALUES = [
    'content-type', 'host', 'x-amz-date', 'user-agent',
    'x-amz-security-token', 'x-amz-access-token',
]
AMAZON_HASH_ALGORITHM = 'AWS4-HMAC-SHA256'
AMAZON_DATETIME_FORMAT = '%Y%m%dT%H%M%SZ'
AMAZON_DATE_FORMAT = '%Y%m%d'

# Inventory / quantitative integration static values
STATIC_SUM_SYSTEM_PRODUCT_NAME = 'Parduotų prekių savikaina'
STATIC_SUM_PRODUCT_CODE = 'AMZPRI'
INVENTORY_WRITE_OFF_REASONS = [
    ('customerDamagedQuantity', 'Quantity damaged by customer'),
    ('warehouseDamagedQuantity', 'Quantity damaged in warehouse'),
    ('distributorDamagedQuantity', 'Quantity damaged by distributor'),
    ('carrierDamagedQuantity', 'Quantity damaged by carrier'),
    ('defectiveQuantity', 'Defective quantity'),
    ('expiredQuantity', 'Expired quantity'),
]
DEFAULT_INVENTORY_REASON_TO_STOCK_REASON_MAPPING = {
    'customerDamagedQuantity': 'reason_line_3',
    'warehouseDamagedQuantity': 'reason_line_3',
    'distributorDamagedQuantity': 'reason_line_3',
    'carrierDamagedQuantity': 'reason_line_3',
    'defectiveQuantity': 'reason_line_1',
    'expiredQuantity': 'reason_line_12',
}

# Other optimal static values suggested by Amazon
# if actually needed - can be later moved to config parameters
MAX_DATA_FETCHING_TTL = 7200
THROTTLE_REPEAT_COUNT = 15

CSV_IMPORT_HEADERS = [
    'Marketplace ID', 'Merchant ID', 'Order Date', 'Transaction Type', 'Is Invoice Corrected', 'Order ID',
    'Shipment Date', 'Shipment ID', 'Transaction ID', 'ASIN', 'SKU', 'Quantity', 'Tax Calculation Date',
    'Tax Rate', 'Product Tax Code', 'Currency', 'Tax Type', 'Tax Calculation Reason Code',
    'Tax Reporting Scheme', 'Tax Collection Responsibility', 'Tax Address Role', 'Jurisdiction Level',
    'Jurisdiction Name', 'OUR_PRICE Tax Inclusive Selling Price', 'OUR_PRICE Tax Amount',
    'OUR_PRICE Tax Exclusive Selling Price', 'OUR_PRICE Tax Inclusive Promo Amount',
    'OUR_PRICE Tax Amount Promo', 'OUR_PRICE Tax Exclusive Promo Amount', 'SHIPPING Tax Inclusive Selling Price',
    'SHIPPING Tax Amount', 'SHIPPING Tax Exclusive Selling Price', 'SHIPPING Tax Inclusive Promo Amount',
    'SHIPPING Tax Amount Promo', 'SHIPPING Tax Exclusive Promo Amount', 'GIFTWRAP Tax Inclusive Selling Price',
    'GIFTWRAP Tax Amount', 'GIFTWRAP Tax Exclusive Selling Price', 'GIFTWRAP Tax Inclusive Promo Amount',
    'GIFTWRAP Tax Amount Promo', 'GIFTWRAP Tax Exclusive Promo Amount', 'Seller Tax Registration',
    'Seller Tax Registration Jurisdiction', 'Buyer Tax Registration', 'Buyer Tax Registration Jurisdiction',
    'Buyer Tax Registration Type', 'Buyer E Invoice Account Id', 'Invoice Level Currency Code',
    'Invoice Level Exchange Rate', 'Invoice Level Exchange Rate Date', 'Converted Tax Amount',
    'VAT Invoice Number', 'Invoice Url', 'Export Outside EU', 'Ship From City', 'Ship From State',
    'Ship From Country', 'Ship From Postal Code', 'Ship From Tax Location Code', 'Ship To City',
    'Ship To State', 'Ship To Country', 'Ship To Postal Code', 'Ship To Location Code', 'Return Fc Country',
    'Is Amazon Invoiced', 'Original VAT Invoice Number', 'Invoice Correction Details',
    'SDI Invoice Delivery Status', 'SDI Invoice Error Code', 'SDI Invoice Error Description',
    'SDI Invoice Status Last Updated Date', 'EInvoice URL'
]
