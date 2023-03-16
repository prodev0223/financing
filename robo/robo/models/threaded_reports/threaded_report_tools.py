# -*- coding: utf-8 -*-
from odoo import _

# Tools used for threaded pivot/materialized reports
# Be sure to add a mapping in all dicts when adding new threaded views

MODEL_TO_THREADED_ACTION_MAPPING = {
    'account.invoice.report.materialized': {
        'general': 'robo.account_invoice_report_materialized_action_threaded',
        'charts': 'robo.account_invoice_report_materialized_action_chart',
    },
}

MODEL_TO_ACTION_MAPPING = {
    'account.invoice.report.materialized': {
        'general': 'robo.account_invoice_report_materialized_action_main',
        'charts': 'robo.account_invoice_report_materialized_action_chart',
    },
}

EXTRA_ID_REDUCER = {
    'account.invoice.report.materialized': {
        'substitute': 'charts',
        'values': ['due', 'due_exp', 'all', 'all_exp']
    }
}

ADDITIONAL_CONTEXT_MAPPING = {
    'account.invoice.report.materialized': {
        'due': {
            'search_default_customer': 1,
            'pivot_measures': ['residual'],
            'search_default_due': 1,
        },
        'due_exp': {
            'search_default_supplier': 1,
            'search_default_due': 1,
            'pivot_measures': ['residual'],
        },
        'all': {
            'search_default_customer': 1,
            'pivot_measures': ['residual'],
        },
        'all_exp': {
            'search_default_supplier': 1,
            'pivot_measures': ['residual'],
        }
    }
}

MODEL_TO_NAME_MAPPING = {
    'account.invoice.report.materialized': _('Sąskaitų analitika')
}

# Used to map model name to date field in the model used for period limiting
MODEL_TO_DATE_MAPPING = {
    'account.invoice.report.materialized': 'date'
}

THREADED_MODELS = ['account.invoice.report.materialized']


def get_action(model, threaded=False, extra_identifier=False):
    """
    Get action from the mapping based on model and extra identifier
    :param model: model of the report
    :param threaded: signifies whether system operates in threaded or non threaded report mode
    :param extra_identifier: identifies the action, if same model uses several
    :return: action ext_id (str)
    """
    mapping_to_use = MODEL_TO_THREADED_ACTION_MAPPING if threaded else MODEL_TO_ACTION_MAPPING
    action_data = mapping_to_use.get(model)

    action_ext_id = action_data
    if isinstance(action_data, dict):
        if not extra_identifier:
            action_ext_id = action_data['general']
        else:
            if extra_identifier in EXTRA_ID_REDUCER[model].get('values', []):
                extra_identifier = EXTRA_ID_REDUCER[model].get('substitute')
            action_ext_id = action_data[extra_identifier]
    return action_ext_id


def get_extra_context(model, extra_identifier):
    """
    Get context from the mapping based on model and extra identifier
    :param model: model of the report
    :param extra_identifier: identifies the context, if same model uses several actions
    :return: extra_context (dict)
    """
    context_data = ADDITIONAL_CONTEXT_MAPPING.get(model, {}).get(extra_identifier, {})
    return context_data
