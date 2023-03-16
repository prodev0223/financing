# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Lithuanian Work Schedule Analytics',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Localization/Account Charts',
    'description': """
Manage payroll analytics with work schedule.
==================================================================================
    """,
    'depends': ['work_schedule', 'robo_analytic'],
    'demo': [],
    'data': [
            'views/analytics.xml',
             ],
    'qweb': [
    ],
    'auto_install': False,
    'installable': True,
}
