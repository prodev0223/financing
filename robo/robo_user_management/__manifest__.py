# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Robolabs User Management',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Other',
    'description': """
Easy user management for front end users
==================================================================================
    """,
    'depends': ['e_document'],
    'demo': [],
    'data': [
        'data/ir.model.csv',
        'security/robo_user_management_groups.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/hr_employee_views.xml',
        'views/mail_channel_views.xml'
    ],
    'qweb': [
        'static/src/xml/*.xml'
    ],
    'auto_install': True,
    'installable': True,
}
