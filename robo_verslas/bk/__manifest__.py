# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'bk',
    'version': '1.0',
    'author': 'Robolabs',
    'category': 'Other',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """
    Papildinys klientui "Burokėlis ir krapas"
""",
    'depends': ['e_document', 'robo_mrp', 'r_keeper', 'work_schedule_analytics'],
    'data': [
        'views/e_document.xml',
        'wizard/account_braintree_bk_import_views.xml'
    ],
    'active': False,
    'installable': True
}
