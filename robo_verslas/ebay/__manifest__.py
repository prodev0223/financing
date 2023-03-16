# -*- coding: utf-8 -*-
# (c) 2021 Robolabs
{
    'name': 'eBay Integration',
    'version': '1.0',
    'author': 'Robolabs',
    'category': 'Other',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'description': """eBay module that provides CSV import""",
    'depends': ['robo'],
    'data': [
        'data/product_category_data.xml',
        'data/product_template_data.xml',
        'data/ebay_currency_mapper_data.xml',
        'data/ebay_configuration_data.xml',
        'security/ir.model.access.csv',
        'views/menu_items.xml',
        'views/ebay_configuration_views.xml',
        'views/ebay_tax_rule_views.xml',
        'views/ebay_import_job_views.xml',
        'views/ebay_order_views.xml',
        'views/ebay_currency_mapper_views.xml',
        'wizard/ebay_order_import_wizard_views.xml',
        'wizard/robo_company_settings_views.xml',
    ],
    'active': False,
    'installable': True
}
