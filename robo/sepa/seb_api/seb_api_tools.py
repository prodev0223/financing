from odoo import _

API_RECORD_LIMIT = 1000
STATIC_SEB_URL = 'api.bgw.baltics.sebgroup.com'
NON_RAISE_ACTION_TO_RESP_MAPPING = {
    'get_day_before_statements': ['LBR_EOD_STATEMENT_NOT_GENERATED'],
    'get_payment_status_report': ['LBR_NOT_FOUND'],
}
NON_RAISE_ACTION_TO_CODE_MAPPING = {
    'get_payment_status_report': [404],
}
EXTERNAL_FAILURE = 500
FORBIDDEN = [403, 401]
MAX_STATEMENT_DAY_PERIOD = 30
REJECTED_MESSAGE_TO_FORMAT = _('Payment export to SEB was rejected. Error message - {}')

GENERAL_API_RESPONSE_MAPPING = {
    200: _('Request has succeeded.'),
    201: _('Request has succeeded, new resource has been created.'),
    400: _('The request cannot be fulfilled due to bad syntax.'),
    401: _('Invalid SEB API certificate.'),
    403: _('Access to the selected resource is forbidden.'),
    404: _('Specified object was not found in SEB system.'),
    405: _('Request method is known by the server but is not supported by the target resource.'),
    406: _('The request cannot be fulfilled due to bad syntax.'),
    409: _('The request could not be completed due to a conflict with the current state of the target recource.'),
    429: _('You have sent too many requests in a given amount of time.'),
    500: _('Error on SEB server side, try again later.'),
    503: _('Error on SEB server side, try again later.'),
}

POST_REJECT_FILE_LEVEL_ERRORS = {
    'TA01': 'The transmission of the file was not successful - it had to be aborted (for technical reasons)',
    'DS0B': 'Data signature for the format is not available or invalid', 'DS0A': 'Data signature is required',
    'AM12': 'Amount is invalid or missing', 'DU01': 'Request with the same MsgId is already processed',
    'AC02': 'Debtor account number invalid or missing',
    'DS0D': 'The signer certificate is not valid (revoked or not active)',
    'AM20': 'Number of transactions at the Payment Information level is invalid',
    'DU02': 'Payment Information Block is not unique', 'DS0H': 'Signer is not allowed to sign for this account',
    'AM19': 'Number of transactions at the Group level is invalid or missing',
    'AM17': 'Control Sum at the Payment Information level is invalid',
    'CH03': 'Value in Requested Execution Date or Requested Collection Date is too far in the future',
    'NARR': 'BtchBookg is not supported',
    'DTO1': 'Invalid date - not allowed to use multiple different Requested Execution Dates',
    'FF01': 'Dynamic reason pointing to mistake in pain.001 or "File Format incomplete or invalid"',
    'AM16': 'Control Sum at the Group level is invalid',
    'CH04': 'Requested Execution Date or Requested Collection Date is too far in the past',
    'AC03': 'Creditor account number invalid or missing',
    'DS19': 'The user rights (concerning his signature) are insufficient to execute the order',
    'AM14': 'Transaction amount exceeds limits agreed between bank and client'
}

POST_REJECT_PROCESSING_LEVEL_ERRORS = {
    'RR07': 'Remittance information structure does not comply with rules for payment type',
    'FF06': 'Category Purpose code is missing or invalid', 'BE22': 'Creditor name is missing',
    'DS0H': 'Signer is not allowed to sign for this account', 'FF03': 'Payment Type Information is missing or invalid',
    'BE09': 'Country code is missing or invalid',
    'RR10': 'Character set supplied not valid for the country and payment type',
    'RR05': 'Regulatory or Central Bank Reporting information missing, incomplete or invalid',
    'AC11': 'Creditor account currency is invalid or missing', 'AC10': 'Debtor account currency is invalid or missing',
    'RR09': 'Structured creditor reference invalid or missing',
    'NARR': ['Creditor account cannot match Debtor account', 'Creditor bank is not INST reachable',
             'Creditor bank is not SEPA reachable',
             'Express payment is not possible due to local holiday in beneficiary country',
             'Incorrect beneficiary name', 'Payment type is not allowed', 'Payments to creditor account are forbidden',
             'Payments to creditor bank are forbidden', 'Structured or unstructured remittance information required',
             'Unable to process payment: please contact the bank for more information'],
    'AM02': 'Specific transaction amount is greater than allowed maximum',
    'AM03': 'Specified message amount is an non processable currency outside of existing agreement',
    'RC04': 'Creditor bank identifier is invalid or missing',
    'AM04': 'Amount of funds available to cover specified message amount is insufficient',
    'AM05': 'Payment is a duplicate of another payment', 'AG01': 'Transaction forbidden on this type of account',
    'AG03': 'Transaction type not supported/authorized on this account',
    'AM14': 'Transaction amount exceeds limits agreed between bank and client',
    'AG08': 'Transaction failed due to invalid or missing user or access right',
    'FF10': 'File or transaction cannot be processed due to technical issues at the bank side',
    'BE19': 'Charge bearer code for transaction type is invalid',
    'DS19': 'The users rights (concerning his signature) are insufficient to execute the order',
    'CNOR': 'Creditor bank is not registered under this BIC in the CSM',
    'BE15': 'Identification code missing or invalid',
    'BE16': 'Debtor or Ultimate Debtor identification code missing or invalid',
    'BE17': 'Creditor or Ultimate Creditor identification code missing or invalid',
    'TM01': 'Payment was received after agreed processing cut-off time',
    'RR12': 'Invalid or missing identification required within a particular country or payment type',
    'AC05': 'Debtor account number closed',
    'AC06': 'Account specified is blocked, prohibiting posting of transactions against it',
    'AC07': 'Creditor account number closed', 'AM11': 'Transaction currency is invalid or missing',
    'AC01': 'Account number is invalid or missing', 'AC02': 'Debtor account number invalid or missing',
    'AC03': 'Creditor account number invalid or missing', 'AM12': 'Amount is invalid or missing',
    'AC09': 'Account currency is invalid or missing',
    'DS04': 'The order was rejected by the bank side (for reasons concerning content)',
    'RC06': 'Debtor BIC identifier is invalid or missing'
}
