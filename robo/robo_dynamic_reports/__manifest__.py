# -*- encoding: utf-8 -*-

{
    'name': 'Robo dynamic reports',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Reporting',
    'description': """
Robo dynamic reports
    """,
    'depends': ['ilgalaikis_turtas', 'account_dynamic_reports', 'sl_general_report'],
    'data': [
        'data/dynamic.report.column.csv',
        'data/dr.group.by.field.csv',

        'views/assets.xml',
        'views/account_asset_dynamic_report_templates.xml',
        'views/invoice_registry_dynamic_report_templates.xml',
        'views/cash_flow_dynamic_report_templates.xml',

        'wizard/account_asset_dynamic_report_views.xml',
        'wizard/general_ledger_dynamic_report_views.xml',
        'wizard/invoice_registry_dynamic_report_views.xml',
        'wizard/accounting_report_views.xml',
        'wizard/account_cashflow_report_views.xml',
        'wizard/account_aged_trial_balance.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': True,
    'installable': True,
}
