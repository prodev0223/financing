# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Multiple Category Uom',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Stock',
    'description': """
This is the module to manage multiple uoms for same product.
==================================================================================
    """,
    'depends' : ['robo_stock'],  # has to depend on robo stock, otherwise account invoice will be created wrongly
    'demo' : [],
    'data' : [
              'security/ir.model.access.csv',
              'views/product.xml',
              'views/sale.xml',
              'views/stock.xml',
              'views/invoice.xml',
              'views/purchase.xml',
              'report/report.xml',
    ],
    'auto_install': False,
    'installable': True,
}
