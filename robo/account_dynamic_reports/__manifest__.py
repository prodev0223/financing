# -*- coding: utf-8 -*-
{
    'name': 'Account Dynamic Reports',
    'version': '1.0',
    'summary': 'Account Dynamic Reports',
    'sequence': 15,
    'description': """""",
    'category': 'Accounting/Accounting',
    'author': 'RoboLabs',
    'maintainer': 'RoboLabs',
    'website': 'https://www.robolabs.lt',
    'images': ['static/description/images/banner.gif'],
    'depends': ['account', 'robo', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'security/dynamic_report_global_settings_security.xml',
        'security/dynamic_report_settings_security.xml',
        'security/dynamic_report_user_column_settings_security.xml',

        'views/assets.xml',
        'views/report.xml',
        'views/views.xml',
        'views/res_currency_views.xml',
        'views/dynamic_report_pdf_templates.xml',

        'wizard/dynamic_report_global_settings_setter_views.xml',
        'wizard/dynamic_report_settings_setter_views.xml',
        'wizard/dynamic_report_pdf_export_views.xml',
    ],
    'demo': [],
    'qweb': [
        'static/src/xml/dynamic_report_data_templates.xml',
        'static/src/xml/dynamic_report_header_templates.xml',
        'static/src/xml/dynamic_report_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
