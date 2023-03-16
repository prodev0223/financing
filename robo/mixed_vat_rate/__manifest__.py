# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    "name": "Mixed VAT rates",
    "version": "0.3",
    "author": "RoboLabs",
    "category": "Misc",
    "website": "http://www.robolabs.lt",
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'security/ir.model.access.csv',
        'security/res_groups.xml',
        'views/company_settings.xml',
        'views/invoice.xml',
    ],
    'installable': True,
    'auto_install': False,
}
