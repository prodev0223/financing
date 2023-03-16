# -*- coding: utf-8 -*-
{
    'name' : 'Mėsos Guru',
    'version' : '1.0',
    'description': """
        Papildinys klientui "Mėsos Guru"
                """,
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'data/mg_unloading_address_data.xml',
        'data/mg_butchery_address_data.xml',
        'views/account_invoice_views.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}
