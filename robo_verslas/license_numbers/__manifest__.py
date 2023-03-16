# -*- coding: utf-8 -*-
{
    'name': 'Company License numbers',
    'version': '1.0',
    'description': """
        Company License numbers"
                """,
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'views/account_invoice_views.xml',
        'views/res_partner_views.xml',
        'report/account_invoice_templates.xml',
        'wizard/robo_company_settings_views.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}
