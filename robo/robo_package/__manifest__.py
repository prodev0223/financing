# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Robo package',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['robo_stock'],
    'demo': [],
    'data': [
            'security/groups.xml',
            'data/header_buttons.xml',
            'view/package.xml',
            'view/assets.xml',
            'security/ir.model.access.csv',
            'data/header_buttons_items.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}

