# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'cherrymusic',
    'version' : '1.0',
    'author' : 'Robolabs',
    'category' : 'Other',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
        Extensions for etaksi client
""",
    'depends' : ['robo', 'robo_ux'],
    'data' : [
        'data/account_invoice_action_data.xml',
        'views/account_journal_views.xml',
        'reports/account_invoice_report_views.xml',
    ],
    'active': False,
    'installable': True
}
