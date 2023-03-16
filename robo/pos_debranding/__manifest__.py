# -*- coding: utf-8 -*-
{
    'name': "POS debranding",
    'version': '1.0',
    'author': 'ITROOTS ODOO',
    'category': 'Debranding',
    'depends': ['point_of_sale'],
    'price': 10.00,
    'currency': 'EUR',
    'data': [
        'views/views.xml',
        ],
    'qweb': [
        'static/src/xml/pos_debranding.xml',
    ],
    'installable': True,
}
