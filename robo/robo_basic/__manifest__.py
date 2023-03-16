# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Settings',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Base',
    'depends': ['robo_depend', 'two_factor_otp_auth', 'account', 'sales_team', 'mrp', 'hr', 'queue_job_cron',
                'hr_expense', 'hr_payroll', 'hr_holidays'],
    'data': [
        'data/front.res.groups.category.csv',
        'security/robo_basic_groups.xml',
        'security/robo_basic_security.xml',
        'data/robo_bug.xml',
        'data/views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
