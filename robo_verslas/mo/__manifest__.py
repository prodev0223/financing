# -*- coding: utf-8 -*-
{
    'name' : 'MO Muziejus',
    'version' : '1.0',
    'description': """
        Papildinys klientui "MO MUZIEJUS"
                """,
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo_analytic', 'robo_stock', 'nsoft'],
    'data': [
        'data/account.financial.report.csv',
        'reports/invoice.xml',
        'views/views.xml',
        'security/res_groups.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}