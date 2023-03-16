# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'Ilgalaikis Turtas',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Base',
    'description': """
Ilgalaikio turto modulis pritaikomas lietuviškai apskaitai.
    """,
    'depends' : ['account_asset', 'l10n_lt', 'robo'],
    'demo' : [],
    'data' : [
        'security/groups.xml',
        'security/ir.model.access.csv',

        'view/assets.xml',
        'view/account_asset_asset_views.xml',
        'view/account_invoice_views.xml',
        'view/account_asset_category_views.xml',
        'view/account_invoice_line_views.xml',
        'view/robo_company_settings_views.xml',

        'data/account.asset.category.csv',
        'report/report.xml',
        'report/account_asset_responsible_report.xml',
        'wizard/wizard.xml',
        'wizard/account_asset_change_wizard_views.xml',
        'wizard/asset_modify_views.xml',
        'wizard/asset_production_wizard_views.xml',
        'wizard/asset_assign_responsible_views.xml',
        'wizard/account_asset_write_off_wizard_views.xml',
        'wizard/account_config_settings_views.xml',
        'wizard/account_asset_sell_wizard_views.xml',
        'wizard/account_asset_merge_wizard_views.xml',
        'wizard/turto_sarasas_wizard_views.xml',

        'data/account_journal_data.xml',
        'data/ir_values_data.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron.xml',

    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}
