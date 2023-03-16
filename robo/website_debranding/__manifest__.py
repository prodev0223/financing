# -*- coding: utf-8 -*-
{
    'name': "Website debranding",
    'version': '1.0',
    'author': 'ITROOTS ODOO',
    'category': 'Debranding',
    'website': 'https://twitter.com/yelizariev',
    'price': 20.00,
    'currency': 'EUR',
    'depends': ['website',
                # 'backend_debranding'
                ],
    'data': [
        'views/views.xml',
    ],
    'auto_install': True,
    'installable': True
}
