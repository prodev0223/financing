# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'PVM sąskaitos-faktūros',
    'version' : '1.0',
    'author' : 'Robolabs',
    'category' : 'Accounting & Finance',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """

""",
    'depends' : ['account', 'base', 'l10n_lt', 'purchase', 'controller_report_xls', 'robo_core'],
    'data' : [
        'assets.xml',
        'imone.xml',
        'report.xml',
        'report_aktas.xml',
        'data/mail_templates.xml',
        'report/invoice_registry.xml',
        'wizard/wizard.xml',
    ],
    'active': False,
    'installable': True
}
