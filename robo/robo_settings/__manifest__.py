# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Settings',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Reporting',
    'depends': ['robo', 'base_import', 'contacts'],
    'data': [
        'data/settings.xml',
        'assets.xml',
    ],
    # 'js': ['static/src/js/session.js'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
