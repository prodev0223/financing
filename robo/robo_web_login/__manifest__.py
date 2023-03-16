# -*- coding: utf-8 -*-
# (c) 2021 Robolabs
{
    'name': 'Robo Web Login Screen',
    'version': '1.3',
    'category': 'Website',
    'summary': """
Naujas Robo web login langas
""",
    'author': "UAB Robolabs",
    'website': 'http://www.robolabs.lt  ',
    'license': 'Other proprietary',
    'depends': ['web'],
    'data': [
        'data/ir_config_parameter.xml',
        'templates/webclient_templates.xml',
        'templates/website_templates.xml',
    ],
    'qweb': [
    ],
    'installable': True,
    'application': True,
}
