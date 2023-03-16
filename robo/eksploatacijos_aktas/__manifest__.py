# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Eksploatacijos aktas',
    'version' : '1.0',
    'author' : 'Robolabs',
    'category' : 'Accounting & Finance',
    'license': 'Other proprietary',
    'website': 'http://www.robolabs.lt',
    'description': """

""",
    'depends' : ['robo_settings', 'ilgalaikis_turtas'],
    'data' : [
        'data/mail_channels.xml',
        'views/account_asset_asset_views.xml',
        'views/alignment_committee_views.xml',
        'views/eksploatacijos_aktas_views.xml',
        'views/robo_company_settings.xml',
        'wizard/operation_act_wizard.xml',
        'security/ir.model.access.csv',
        'report_qweb/report.xml',
    ],
    'installable': True
}
