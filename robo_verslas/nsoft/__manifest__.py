# -*- coding: utf-8 -*-
{
    'name': 'nSoft',
    'version': '1.0',
    'description': """
        Papildinys klientui "nSoft"
                """,
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'data/accounting_data.xml',
        'data/sum_accounting_data.xml',
        'data/config_parameters.xml',
        'data/cron_jobs.xml',
        'data/robo_header_data.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/base.xml',
        'views/nsoft_sale_line.xml',
        'views/nsoft_invoice.xml',
        'views/nsoft_cash_register.xml',
        'views/nsoft_payment_type.xml',
        'views/nsoft_payment.xml',
        'views/nsoft_receipt_report.xml',
        'views/nsoft_cash_operation_views.xml',
        'views/nsoft_cashier_mapper_views.xml',
        'views/product_template.xml',
        'views/res_partner_views.xml',
        'views/account_payment_views.xml',
        'views/sum_accounting/nsoft_product_category.xml',
        'views/sum_accounting/nsoft_report_move.xml',
        'views/sum_accounting/nsoft_report_move_line.xml',
        'views/sum_accounting/nsoft_report_move_category.xml',
        'views/sum_accounting/nsoft_purchase_invoice.xml',
        'views/sum_accounting/nsoft_warehouse_views.xml',
        'views/robo_company_settings.xml',
        'wizard/nsoft_import_wizard.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
}