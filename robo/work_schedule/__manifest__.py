# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Work Schedule',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Timesheets',
    'description': """
This is the module to manage the work schedule for Lithuania.
==================================================================================
    """,
    'depends': ['e_document', 'l10n_lt_payroll'],
    'demo': [],
    'data': [
        'data/work_schedule_parameters.xml',
        'data/work.schedule.codes.csv',
        'data/work_schedules.xml',
        'data/ir_crons.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_channels.xml',
        'views/assets.xml',
        'views/e_document_views.xml',
        'views/company_settings.xml',
        'views/schedule_setters_view.xml',
        'views/backend_schedule_view.xml',
        'views/main_schedule_view.xml',
        'views/work_schedule_views.xml',
    ],
    'qweb': [
        'static/src/xml/*.xml'
    ],
    'auto_install': False,
    'installable': True,
}
