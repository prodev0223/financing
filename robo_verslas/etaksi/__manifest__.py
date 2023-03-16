# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'eTaksi',
    'version' : '1.0',
    'author' : 'Robolabs',
    'category' : 'Other',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
        Extensions for etaksi client
""",
    'depends' : ['robo'],
    'data' : [
        'data/account_invoice_action_data.xml',
        'views/account_invoice_views.xml',
        'views/account_journal_views.xml',
        'reports/account_invoice_report_views.xml',
        'views/etaksi_data_import_job.xml',
        'views/etaksi_invoice_mass_mailing.xml',
        'views/etaksi_invoice_mass_mailing_job.xml',
        'wizard/etaksi_data_import.xml',
        'views/menuitems.xml',
        'security/res.groups.xml',
        'security/record.rules.xml',
        'security/ir.model.access.csv',
    ],
    'active': False,
    'installable': True
}
