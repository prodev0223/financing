# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Region manager signable e-documents',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Misc',
    'description': """
E-documents made signable for region managers
==================================================================================
    """,
    'depends': ['e_document'],
    'demo': [],
    'data': [
        'views/assets.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record.rules.xml',
        'views/e_document_region_manager_views.xml',
        'views/robo_company_settings_views.xml',
        'views/e_document_views.xml',
        'views/robo_header_items.xml',
        'views/hr_employee_views.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}
