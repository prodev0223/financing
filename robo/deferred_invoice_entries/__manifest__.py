# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    "name": "Deferred invoice entries",
    "author": "Robolabs",
    "license": "Other proprietary",
    "complexity": "normal",
    "description": """

    """,
    "category": "",
    "depends": [
        'robo_depend',
        'base',
        'account',
        'sale',
        'robo_basic'
    ],
    "data": [
        'views/account_invoice_deferred_view.xml',
        'security/ir.model.access.csv',
    ],
    "qweb": [
        'static/src/xml/base.xml',
    ],
    "installable": True,
}
