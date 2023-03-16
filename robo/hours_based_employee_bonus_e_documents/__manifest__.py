# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Hours worked based employee bonus e-document',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Misc',
    'description': """
Allow creating bonuses based on hours worked for e-document employee bonus document
==================================================================================
    """,
    'depends': ['e_document'],
    'demo': [],
    'data': [
        'e_document_templates/orders/del_priedo_skyrimo_grupei/del_priedo_skyrimo_grupei.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': [],
    'auto_install': False,
    'installable': True,
}
