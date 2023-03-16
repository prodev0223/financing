# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Password Security',
    'author': 'RoboLabs',
    'category': 'Robo',
    'depends': [
        'auth_signup',
    ],
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'data': [
        'views/res_company.xml',
    ],
    'test': [
        'tests/company.yml',
    ],
    'installable': True,
    'auto_install': False,
}
