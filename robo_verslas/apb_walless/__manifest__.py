# -*- coding: utf-8 -*-
{
    'name' : 'APB WALLESS',
    'version' : '1.0',
    'description': """
        Papildinys klientui "WALLESS"
                """,
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'data/robo_header.xml',
        'data/ir_cron.xml',
        'security/res_groups.xml',
        'views/walless_royalty_sheet.xml',
        'views/walless_royalty_sheet_line.xml',
        'views/hr_employee.xml',
        'views/hr_job.xml',
        'views/res_partner.xml',
        'views/accounts.xml',
        'wizard/walless_psd_sepa_export.xml',
        'views/menuitems.xml',
        'views/report.xml',
        'security/ir.model.access.csv',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}