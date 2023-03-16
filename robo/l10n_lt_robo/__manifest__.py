# -*- coding: utf-8 -*-
# (c) 2021 RoboLabs

{
    'name': 'Lithuanian RoboLabs front-end',
    'version': '1.0',
    'author': 'RoboLabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
RoboLabs front-end module localised for Lithuania
    """,
    'depends': ['robo', 'l10n_lt'],
    'data': [
        'views/account_move_views.xml',
        'views/account_move_line_views.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'installable': True,
    'auto_install': False,

}
