# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Robo electronics',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['robo_stock'],
    'demo': [],
    'data': [
            'security/groups.xml',
            'data/header_buttons.xml',
            'view/electronics.xml',
            'view/assets.xml',
            'data/header_buttons_items.xml',
            'security/ir.model.access.csv'
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}

