# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Stock Orders',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['robo_stock'],
    'demo': [],
    'data': [
        'security/groups.xml',
        'views/views.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}
