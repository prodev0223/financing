# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Nurašymo aktas',
    'version' : '1.0',
    'author' : 'RoboLabs',
    'category' : 'Accounting & Finance',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends' : ['eksploatacijos_aktas'],
    'data' : [
        'security/ir.model.access.csv',
        'report_qweb/assets.xml',
        'report_qweb/report.xml',
    ],
    'installable': True
}
