# -*- coding: utf-8 -*-
from odoo import _

GENERAL_API_RESPONSE_MAPPING = {
    200: _('Request has succeeded.'),
    201: _('Request has succeeded, new resource has been created.'),
    422: _('The request cannot be fulfilled due to bad syntax.'),
    401: _('Invalid Enable banking API key.'),
    403: _('Access to the selected resource is forbidden.'),
    404: _('Specified object was not found in Enable banking system.'),
    429: _('You have sent too many requests in a given amount of time.'),
    500: _('Error on Enable banking server side, try again later.'),
}
# Base/main external failure code
EXTERNAL_FAILURE = 500
# Other external failure codes
EXTERNAL_FAILURE_CODES = [
    504, EXTERNAL_FAILURE,
]

MAX_TOKEN_TTL_SECONDS = 7776000
MAX_TRANSACTION_FETCHING_TTL = 7200

# Mapping of bank BICs to API bank name
# (List of available connectors, for most part will remain static)
CONNECTOR_BANK_BIC_MAPPING = {
    'cit_lt': {'bic_code': 'INDULT2X'},
    'sib_lt': {'bic_code': 'CBSBLT26XXX', 'related_bic_codes': ['CBSBLT26']},
    'lum_lt': {'bic_code': 'AGBLLT2X'},
    'seb_lt': {'bic_code': 'CBVILT2X'},
    # 'swed_lt': {'bic_code': 'HABALT22'},  # TODO: Disable Swed-bank connector for now
    'rev_lt': {'bic_code': 'RETBLT21XXX', 'related_bic_codes': ['RETBLT21XXX', 'REVOGB21XXX']},
}

# Code mapping to res.partner fields
BANK_PARTNER_CODE_TYPE_MAPPER = {
    'COID': 'kodas',
    'TXID': 'vat',
}

EXTERNAL_FAILURE_RESPONSES = [
    'ASPSP_ERROR',
    'LBR_SERVICE_UNAVAILABLE',
]

AUTHORIZATION_FAILURE = 'ASPSP_UNAUTHORIZED_ACCESS'
EXPIRED_SESSION = 'EXPIRED_SESSION'

# Balance type identifiers
ACCOUNTING_BALANCE = 'CLBD'
INTERIM_BOOKED_BALANCE = 'ITBD'
INTERIM_BALANCE = 'ITAV'

