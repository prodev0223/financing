# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Lithuanian Intrastat Declaration',
    'version': '1.0',
    'author' : 'Robolabs',
    'category': 'Localization',
    'license': 'Other proprietary',
    'description': """

    """,
    'depends': ['report_intrastat', 'sale_stock', 'account_accountant', 'l10n_lt', 'report_intrastat'],
    'data': [
        'data/report.intrastat.code.csv',  # noupdate
        'data/transaction.codes.xml',
        'data/transport.modes.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'l10n_lt_intrastat.xml',
        'wizard/l10n_lt_intrastat_declaration_view.xml',
    ],
    'installable': True,
}
