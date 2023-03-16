# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Account Move Import',
    'license': 'Other proprietary',
    'author': 'RoboLabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Accounting & Finance',
    'summary': 'Import Accounting Entries',
    'depends': ['account'],
    'data': [
        'views/account_move.xml',
        'wizard/import_move_line_wizard.xml',
    ],
    'demo': [
        # 'demo/account_move.xml',
    ],
    'installable': True,
}
