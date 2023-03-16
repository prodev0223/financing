# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'ROBO DEMO',
    'version': '1.0',
    'author': 'Robolabs',
    'category': 'Misc',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """

""",
    'depends': ['robo', 'sessions', 'robo_user_management'],
    'data': [
        'views/demo.xml',
        'views/assets.xml',
        'views/views.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'installable': True
}
