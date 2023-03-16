# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Robo Accounting Consistency Tests',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Localization/Account Charts',
    'description': """
This is the module to check accounting consistency and edit dates.
==================================================================================
    """,
    'depends' : ['l10n_lt', 'stock_extend'],
    'demo' : [],
    'data' : [
              'security/ir.model.access.csv',
              'views/account_consistency_view.xml',
              'views/invoice_picking_date_consistency_view.xml',
              'views/stock_to_accounting_matcher_views.xml',
    ],
    'auto_install': False,
    'installable': True,
}
