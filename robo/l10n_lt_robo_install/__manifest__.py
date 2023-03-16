# -*- coding: utf-8 -*-
# (c) 2021 RoboLabs

{
    'name': 'Lithuanian RoboLabs install',
    'version': '1.0',
    'author': 'RoboLabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
RoboLabs installation for Lithuanian localisation
    """,
    'depends': ['robo_install', 'l10n_lt_robo'],
    'data': [
    ],
    'qweb': ['static/src/xml/*.xml'],
    'installable': True,
    'auto_install': False,

}
