# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Stock Summary Report',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Other',
    'depends' : ['purchase', 'stock_extend', 'read_group_full_expand'],
    'demo' : [],
    'data' : [
              'view/analysis.xml',
              'view/views.xml',
              'security/ir.model.access.csv'],
    'auto_install': False,
    'installable': True,
}
