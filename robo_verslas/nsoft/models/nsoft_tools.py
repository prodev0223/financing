# -*- coding: utf-8 -*-

ALLOWED_TAX_CALC_ERROR = 0.1
DATED_SALE_DATE = '2019-02-01'
STATIC_ACCOUNT_CODE = '2410'
PAYMENT_CODES_TO_SKIP = ['A']
NON_INVOICED_PRODUCT_CODES = ['1KUP0312']

VAT_RATE_TO_CODE_MAPPER = {
    0.0: 'PVM5',
    9.0: 'PVM2',
    21.0: 'PVM1'
}

SPEC_SUM_DOC_TYPE = 9

DEFAULT_SUM_REPORT_ACCOUNTS = {
    2: '6000',
    6: '652',
    7: '60062'
}


FIELD_TO_READABLE_MAPPING = {
    'amount_tax': 'PVM Suma',
    'amount_untaxed': 'Suma be PVM',
    'amount_total': 'Galutinė suma'
}

REPORT_FIELD_NAME_MAPPING = {
    2: {'amount': 'sold_amount', 'qty': 'sold_qty'},
    6: {'amount': 'inv_amount', 'qty': 'inv_qty'},
    7: {'amount': 'writeoff_amount', 'qty': 'writeoff_qty'},
}
