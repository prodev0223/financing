# -*- coding: utf-8 -*-
{
    'name': 'Robo Reports',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Reporting',
    'description': """
Robo Reports
        """,
    'depends': ['report'],
    'data': [
        'data/report_paperformat.xml',
    ],
    'qweb' : [
        'static/src/xml/*.xml',
    ],
    'auto_install': False,
    'installable': True
}
