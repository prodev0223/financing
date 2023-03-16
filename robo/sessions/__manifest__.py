# -*- encoding: utf-8 -*-


{
    'name': 'Web Sessions Management',
    'summary': '',
    'description': 'Sessions timeout and forced termination. Multisession control. Login by calendar (week day hours). Remote IP filter and location.',
    'author': 'TKO,RoboLabs',
    'category': 'Extra Tools',
    'version': '10.0.0.0.0',
    'application': False,
    'external_dependencies': {
         'python': ['redis'],
     },
    'installable': True,
    'auto_install': False,
    'depends': [
                'base',
                'resource',
                'web',
                'robo_depend',
                'robo_web_login',
                'auth_signup',
    ],
    'external_dependencies': {
                                'python': [],
                                'bin': [],
                                },
    'init_xml': [],
    'update_xml': [],
    'css': [],
    'demo_xml': [],
    'data': [
             'security/ir.model.access.csv',
             'views/scheduler.xml',
             'views/res_users_view.xml',
             'views/res_groups_view.xml',
             'views/ir_sessions_view.xml',
             'views/webclient_templates.xml',
    ],
}
