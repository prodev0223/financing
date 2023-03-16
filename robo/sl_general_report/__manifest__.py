# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': "General reports (RoboLabs)",
    'summary': """
        Some of the default reports overriden to make changes""",

    'description': """
        Some of the default reports overriden to make changes. Mostly accounting reports
    """,

    'author': "RoboLabs",
    'website': "www.robolabs.lt",
    'category': '',
    'depends': ['robo_depend', 'account_accountant', 'skolu_suderinimas'],
    'data': [
        'data/account.financial.report.csv',
        'view/assets.xml',
        'view/general_report.xml',
        'view/kasos_knyga.xml',
        'view/report_kasos_knyga.xml',
        'view/report_cash_receipt.xml',
        'view/report_generalledger_sl.xml',
        'view/report_financial_sl.xml',
        'view/report_trialbalance_sl.xml',
        'view/report_agedpartnerbalance_sl.xml',
        'view/report_cashflowstatement_sl.xml',
        'view/report_delivery_slip.xml',
        'view/report_partnerledger.xml',
        'view/view.xml',
        'view/cashflow_statement.xml',
        'view/debt_report.xml',
        'view/account_financial_report.xml',
        'wizard/account_financial_report_addition_wizard_views.xml',
        'view/account_common_report.xml',
        'report/account_cashflow_report_views.xml',
        'data/cashflow.activity.csv',
        'security/ir.model.access.csv'
    ],
    'qweb': [
        # 'view/report_financial_sl.xml',
    ],
    'css': [
        # 'static/src/css/stylesheet.css'
    ],
    # only loaded in demonstration mode
    'demo': [],
    'installable': True,
}
