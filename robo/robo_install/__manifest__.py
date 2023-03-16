# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Robo install',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Other',
    'description': """

Copyright belongs to Robolabs
==================================================================================
    """,

    'depends': ['periodic_payments', 'account_exchange_rate', 'l10n_lt', 'l10n_lt_payroll',
                'mokejimu_eksportas', 'sepa', 'contacts', 'currency_rate_update', 'purchase_extend',
                'nurasymo_aktas', 'e_ataskaitos', 'due_payments', 'avansine_apyskaita',
                'deferred_invoice_entries', 'auth_brute_force', 'robo', 'robo_settings',
                'saskaitos', 'skolu_suderinimas', 'stock_move_report', 'sodra',
                'stock_extend', 'e_document', 'account_move_import', 'account_multicurrency_revaluation',
                'ilgalaikis_turtas', 'mass_editing', 'robo_accountants', 'passwords',
                'backend_debranding', 'pivot_freeze', 'project_issue', 'robo_web_login', 'mrp'],
    'demo': [],
    'data': [
        'install.xml',
    ],
    'qweb': [
    ],
    'auto_install': True,
    'installable': True,
}

