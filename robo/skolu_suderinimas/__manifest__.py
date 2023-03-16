# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Skolų suderinimo aktas',
    'version' : '1.0',
    'author' : 'RoboLabs',
    'category' : 'Finance',
    'website': 'http://www.robolabs.lt',
    'description': """
""",
    'depends': ['robo_depend', 'account', 'sale', 'crm'],
    'data': ['security/groups.xml',
             'report.xml',
             'wizard/aktas_report.xml',
             'views/report_aktas.xml'
             ],
    'installable': True
}
