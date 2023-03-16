# -*- coding: utf-8 -*-
{
    'name': 'Etsy import',
    'version': '1.0',
    'description': """
        Etsy Data import
                """,
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['l10n_lt'],
    'data': [
        'security/ir.model.access.csv',
        'views/etsy_data_import.xml',
        'views/etsy_data_import_job.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}
