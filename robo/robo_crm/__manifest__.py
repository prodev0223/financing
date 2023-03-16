# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Robo crm',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['crm', 'robo'],
    'demo': [],
    'data': [
        'security/groups.xml',
        'views/robo_crm_activity_log_views.xml',
        'views/robo_crm_stage.xml',
        'views/robo_crm_calendar.xml',
        'views/robo_crm.xml',
        'data/crm_stage_data.xml',
        'data/crm_activity_data.xml',
        'data/utm_data.xml',
        'views/reports.xml',
        # 'view/reports.xml',
        # 'security/ir.model.access.csv',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}
