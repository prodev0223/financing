# -*- coding: utf-8 -*-
{
    'name' : 'Duomenų importavimas',
    'version' : '1.0',
    'description': """
        Duomenų importavimas
                """,
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/back_data_import.xml',
        'views/back_data_import_job.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}