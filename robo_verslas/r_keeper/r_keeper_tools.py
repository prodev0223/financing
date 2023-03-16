# -*- coding: utf-8 -*-
# XLS IMPORT FIELD LISTS

XLS_FIELD_LIST_MAPPING = {
    'payment_type_xls': {
        'all_fields': ['name', 'code', 'do_reconcile', 'journal_type', 'account_type', 'reconcilable_account'],
        'required_fields': ['name', 'code'],
        'boolean_fields': ['do_reconcile', 'reconcilable_account'],
    },
}

WINDOWS_CMD_ERRORS = ['The system cannot find the path specified.']
FETCHED_FILE_EXTENSION = '.eip'
EXPORTED_FILE_EXTENSION = 'upd'

ALLOWED_PAYMENT_JOURNAL_TYPES = ['sale', 'cash', 'general']
ALLOWED_PAYMENT_ACCOUNT_TYPES = ['receivable', 'current_assets']
ACCOUNT_TYPE_MAPPING = {
    'receivable': 'account.data_account_type_receivable',
    'current_assets': 'account.data_account_type_current_assets'
}
