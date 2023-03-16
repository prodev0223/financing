# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Mokėjimų eksportavimas į Sepa',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Accounting & Finance',
    'depends': ['account_bank_statement_import', 'sepa', 'imones_kodas', 'robo_basic'],
    'demo': [],
    'data': ['view/mokejimai_view.xml',
             'view/bank_statement_creation.xml',
             'view/account_move_line.xml',
             'view/account_journal_views.xml',
             'security/ir.model.access.csv',
             'security/record.rules.xml',
             ],
    'auto_install': False,
    'installable': True,
}
