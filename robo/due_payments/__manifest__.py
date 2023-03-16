# -*- coding: utf-8 -*-
# (c) 2021 Robolabs
{
    'name': "Due payments",
    'author': "Robolabs",
    'website': "www.robolabs.lt",
    'license': 'Other proprietary',
    'category': 'Accounting & Finance',
    'description': """
Configure unpaid invoice reminder emails
    """,
    'depends': ['robo_depend', 'account_accountant', 'robo_core'],
    'data': [
        'view/res_partner_views.xml',
        'data/mail_template.xml',
        'data/ir_cron.xml',
    ],
    'demo': [],
    'installable': True,
}
