# -*- coding: utf-8 -*-
{
    'name' : 'WALLESS',
    'version' : '1.0',
    'description': """
        Papildinys klientui "WALLESS"
                """,
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['base', 'robo', 'e_document'],
    'data': [
        'views/views.xml',
        'views/e_document_templates.xml',
        'security/record.rules.xml',
        'security/ir.model.access.csv',
        'data/config_parameters.xml'
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}