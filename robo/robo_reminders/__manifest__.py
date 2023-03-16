# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Robo Reminders',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Localization/Account Charts',
    'description': """
This is the module to send the manager reminders about missing documents.
==================================================================================
    """,
    'depends' : ['robo',],
    'demo' : [],
    'data' : [
              # 'security/ir.model.access.csv',
              'views/robo_reminders_view.xml',
              'views/unreconciled_payments_reminder.xml',
              'report_qweb/unreconciled_payments_report.xml',
    ],
    'auto_install': False,
    'installable': True,
}
