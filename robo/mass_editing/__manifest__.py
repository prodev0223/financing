# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    "name": "Mass Editing",
    "version": "8.0.1.3.0",
    "author": "RoboLabs,Serpent Consulting Services,Odoo Community Association (OCA)",
    "category": "Tools",
    "website": "http://www.serpentcs.com",
    "license": "LGPL-3",
    'depends': ['base'],
    'data': [
        "security/ir.model.access.csv",
        'views/mass_editing_view.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
