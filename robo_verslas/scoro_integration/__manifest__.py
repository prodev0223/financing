# -*- coding: utf-8 -*-
{
    'name': 'Scoro Integration',
    'version': '1.0',
    'description': """
            Integracija su 'Scoro' API
                    """,
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'data/data.xml',
        'views/crons.xml',
        'views/views.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}