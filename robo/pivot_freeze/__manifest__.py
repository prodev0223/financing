# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Pivot Head Fixer',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Reporting',
    'description': """
Lets the user create a custom dashboard.
========================================

Allows users to create custom dashboard.
    """,
    'depends': ['robo_depend', 'web'],
    'data': [
        'views/assets.xml',
    ],
    'qweb': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
