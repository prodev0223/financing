# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Manilla',
    'version' : '1.0',
    'author' : 'Robolabs',
    'category' : 'Other',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
        Extensions for manilla client
""",
    'depends' : ['robo_mrp'],
    'data' : [
        'views/reports.xml',
        'views/views.xml',
        'views/account_invoice_report.xml',
        'views/hr_employee_views.xml'
    ],
    'active': False,
    'installable': True

}