# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'RoboLabs Core',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Base',
    'depends': ['robo_basic', 'report_xlsx'],
    'data': [
        'data/mail_templates.xml',

        'security/record.rules.xml',
    ],
    'installable': True,
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': True,
}
