# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    "name": "Currency Rate Update",
    "author": "RoboLabs",
    "website": "http://robolabs.lt",
    "license": "Other proprietary",
    "category": "Accounting & Finance",
    "depends": [
        "base",
        "account",
    ],
    "data": [
        "view/service_cron_data.xml",
        "view/currency_rate_update.xml",
        "view/company_view.xml",
        "security/rule.xml",
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "active": False,
    'installable': True
}
