# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Robo GPAIS',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Misc',
    'depends': ['robo_electronics', 'robo_package'],
    'demo': [],
    'data': [
            'view/assets.xml',
            'view/gpais_registration_line_views.xml',
            'view/product_battery_views.xml',
            'view/product_package_views.xml',
            'view/product_template_views.xml',
            'view/res_partner_views.xml',
            'view/res_users_views.xml',
            'view/stock_picking_views.xml',
            'wizard/battery_line_remove_wizard_views.xml',
            'wizard/gpais_setting_wizard_views.xml',
            'wizard/gpais_wizard_views.xml',
            'wizard/package_default_remove_wizard_views.xml',
            'wizard/robo_company_settings_views.xml',
            'wizard/uzstatine_pakuote_remove_wizard_views.xml',
            'security/ir.model.access.csv',
            'data/gpais.klasifikacija.csv',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'auto_install': False,
    'installable': True,
}

