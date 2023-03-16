# -*- encoding: utf-8 -*-

# Various Paysera static values
STATIC_NONCE_SIZE = 32
STATIC_PAYSERA_HOST = 'wallet.paysera.com'
STATIC_PAYSERA_PORT = '443'
SIMULATED_TRANSFER_ID = 99999999
STATIC_PAYSERA_BIC = 'EVIULT2VXXX'
RENEW_MESSAGE = 'Token has expired'
REFRESH_RENEW_MESSAGE = 'Refresh token expired'
ACCESS_ERROR = 'No WRITE permissions'
RENEW_CODE = 900
REFRESH_RENEW_CODE = 800
API_RETRY_THRESHOLD = 5
NON_THREADED_RECORD_SIZE = 10
API_RECORD_LIMIT = 200
MANUAL_API_ACTIONS = ['wallet', 'test_api', 'wallet_balance_manual',
                      'post_transfer', 'register_transfer', 'sign_transfer', 'wallet_statements_manual', 'user']

RESOURCE_SCOPES = ['wallet_list_offline', 'balance_offline', 'statements',
                   'statements_offline', 'identity_offline', 'initiate_transfers']

STATIC_PURPOSE_LENGTH = 40
# Extra required fields based on bank bic
# updated by trial and error, since Paysera
# does not provide a clear answer on which banks require what
PAYMENT_INIT_FIELD_RULES_TO_BIC = {
    'REVOGB21XXX': ['address_rule', 'purpose_length_rule'],
    'RETBLT21XXX': ['address_rule', 'purpose_length_rule'],
    'REVOLT21XXX': ['address_rule', 'purpose_length_rule'],
    'BUKBGB22': ['address_rule'],
}
