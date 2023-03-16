# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'UX Customisation',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Extra Tools',
    'description': """
Provides the system with some customisation properties to improve the UX
==================================================================================
    """,
    'depends': ['robo'],
    'demo': [],
    'data': [
        'security/ir.model.access.csv',
        'wizard/set_robo_ux_settings_views.xml',
        'wizard/mail_compose_message_views.xml',
        'views/robo_company_settings_views.xml',
    ],
    'qweb': [
    ],
    'auto_install': True,
    'installable': True,
}
