# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs
{
    'name': 'LastMile',
    'description': """
        Papildinys klientui "LastMile"
                """,
    'author': 'Robolabs',
    'category' : 'Other',
    'license': 'Other proprietary',
    'depends': ['robo', 'sepa'],
    'demo': [],
    'data': [
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'views/revolut_api_views.xml',
        'views/revolut_import_job_views.xml',
    ],
    'auto_install': False,
    'installable': True,
}
