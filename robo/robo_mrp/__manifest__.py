# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'RoboLabs MRP extension',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category': 'Accounting',
    'depends': ['robo_stock'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/robo_mrp_security.xml',

        'data/ir_cron_data.xml',
        'data/ir_sequence_data.xml',
        'data/menuitem_data.xml',
        'data/robo_header_data.xml',

        'report/mrp_bom_templates.xml',
        'report/mrp_bom_reports.xml',

        'wizard/change_production_location_views.xml',
        'wizard/change_production_qty_views.xml',
        'wizard/mrp_bom_export_wizard_views.xml',
        'wizard/mrp_bom_copy_wizard_views.xml',
        'wizard/mrp_production_copy_wizard_views.xml',
        'wizard/mrp_production_copy_wizard_line_views.xml',
        'wizard/mrp_production_surplus_reserve_views.xml',
        'wizard/robo_company_settings_views.xml',
        'wizard/mrp_bom_proportion_wizard_views.xml',

        'views/stock_move_views.xml',
        'views/mrp_bom_line_views.xml',
        'views/mrp_bom_templates.xml',
        'views/mrp_bom_views.xml',
        'views/mrp_unbuild_prices_views.xml',
        'views/mrp_unbuild_views.xml',
        'views/mrp_production_views.xml',
        'views/product_category_views.xml',
        'views/product_product_views.xml',
        'views/product_template_views.xml',
        'views/stock_landed_cost_views.xml',
        'views/mrp_workcenter_productivity_views.xml',
        'views/mrp_workorder_views.xml',

        'data/robo_header_items_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}
