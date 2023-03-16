# -*- encoding: utf-8 -*-

{
    'name': 'Robo Mail Template Manager',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'description': """Controller for customising mail templates""",
    'depends': ['robo'],
    'demo': [],
    'data': [
        'data/ir.model.csv',
        'data/email_templates.xml',

        'views/assets.xml',
        'wizard/mail_template_preview.xml',
        'views/mail_template_views.xml',
        'views/res_users_views.xml',
        'views/robo_company_settings.xml',

        'security/mail_template_security.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}
