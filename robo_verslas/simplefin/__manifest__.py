# -*- coding: utf-8 -*-
{
    'name': 'Simplefin',
    'version': '1.0',
    'description': """
        Papildinys klientui "Simplefin"
                """,
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['base', 'robo'],
    'data': [
        'data/product_category_data.xml',
        'data/product_template_data.xml',

        'views/report.xml',
        'views/account_invoice_views.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}
