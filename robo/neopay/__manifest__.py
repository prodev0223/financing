# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Neopay integration',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Base',
    'depends': ['robo', 'l10n_lt', 'sepa', 'robo_basic', 'saskaitos', 'due_payments'],
    'data': [
        'security/ir.model.access.csv',

        'data/mail_templates.xml',
        
        'views/account_invoice_views.xml',
        'views/online_payment_transaction_views.xml',
        
        'wizard/robo_company_settings_views.xml',
    ],
    'installable': True,
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': True,
}
