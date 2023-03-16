# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Stock extend',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['stock', 'stock_landed_costs', 'stock_account', 'sale_stock', 'robo_basic', 'deferred_invoice_entries'],
    'demo': [],
    'data': [
        'data/data.xml',
        'data/product_uom_data.xml',
        'view/stock_inventory.xml',
        'view/landed_costs.xml',
        'view/sale_order.xml',
        'view/procurement_rule.xml',
        'view/stock_warehouse.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
    ],
    'auto_install': False,
    'installable': True,
}
