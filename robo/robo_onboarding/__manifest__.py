# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Onboarding',
    'version' : '0.1',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Extra Tools',
    'description': """Track the onboarding process of new clients""",
    'depends': ['robo'],
    'data': [
        'data/robo_onboarding_categories.xml',
        'data/robo_onboarding_tasks.xml',
        'views/robo_onboarding_task_views.xml',
        'views/robo_onboarding_category_views.xml',
        'views/robo_onboarding_menus.xml',
        'views/robo_onboarding_statusbar.xml',
        'views/assets.xml',
        'security/ir.model.access.csv'
    ],
    'qweb': ['static/src/xml/*.xml'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
