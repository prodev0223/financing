# -*- encoding: utf-8 -*-

RASO_VATRATE_TO_VATCODE_MAPPER = {
    21: 1,
    5: 2,
    0: 3
}

RESPONSE_STRUCTURE = ['error', 'code', 'system_error', 'data']

API_METHOD_MAPPING = {
    'create_invoice': 'api_create_invoice',
    'unlink_invoice': 'api_unlink_invoice',
    'cancel_invoice': 'api_cancel_invoice',
    'update_invoice': 'api_update_invoice',
    'get_invoice': 'api_get_invoice',
    'get_invoice_list': 'api_get_invoice_list',
    'add_invoice_document': 'api_add_invoice_document',
    'create_product': 'api_create_product',
    'update_product': 'api_update_product',
    'new_products': 'api_get_products_by_date',
    'products': 'api_get_products_by_wh',
    'product_categories': 'api_get_product_categories',
    'create_product_category': 'api_create_product_category',
    'update_product_category': 'api_update_product_category',
    'create_partner_payments': 'api_create_partner_payments',
    'create_accounting_entries': 'api_create_accounting_entries',
    'get_accounting_entries': 'api_get_accounting_entries',
    'write_off_products': 'api_write_off_products',
}

ROBO_API_JOB_STATES = ['to_execute', 'to_retry', 'in_progress', 'succeeded', 'failed']
DATA_IDENTIFIER_FIELDS = ['number', 'reference', 'move_name']

API_SUCCESS = 200
API_INCORRECT_DATA = 400
API_INVALID_CRED = 401
API_FORBIDDEN = 403
API_NOT_FOUND = 404
API_INTERNAL_SERVER_ERROR = 500
API_TOO_MANY_REQUESTS = 429


def process_bool_value(value):
    """
    Check whether passed value can be converted to python'ic boolean, if not, return False
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
