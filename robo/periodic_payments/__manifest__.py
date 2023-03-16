# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Periodiniai mokėjimai',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category' : 'Finance',
    'license': 'Other proprietary',
    'depends' : ['robo_depend', 'account', 'mokejimu_eksportas', 'subscription', 'hr_payroll', 'account_accountant', 'l10n_lt_payroll'],
    'demo' : [],
    'data' : ['view/view.xml',
              'security/ir.model.access.csv',
              'data/sutarciu.rusis.csv',
    ],
    'auto_install': False,
    'installable': True,
}
