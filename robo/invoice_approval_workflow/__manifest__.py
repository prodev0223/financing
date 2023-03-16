# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Invoice approval workflow',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Accounting',
    'description': """
Allows creating account invoice approval workflow that has to be completed before an invoice is approved
    """,
    'depends': ['account', 'robo_basic', 'robo', 'l10n_lt_payroll'],
    'demo': [],
    'data': [
        'security/invoice_approval_groups.xml',
        'security/ir.model.access.csv',
        'security/invoice_approval_security.xml',

        'data/ir_ui_menu.xml',
        'data/ir_cron.xml',
        'data/mail_channels.xml',

        'views/assets.xml',

        'views/invoice_approval_step_views.xml',
        'views/invoice_approver_views.xml',
        'views/invoice_approval_condition_views.xml',

        'views/invoice_approval_workflow_views.xml',
        'views/invoice_approval_workflow_step_approver_views.xml',
        'views/inv_approval_workflow_condition_views.xml',
        'views/invoice_approval_workflow_step_views.xml',
        'views/safety_net_approval_condition_views.xml',

        'views/account_invoice_views.xml',

        'wizard/disapprove_account_invoice_views.xml',
        'wizard/robo_company_settings_views.xml',
        'wizard/invoice_approval_settings_views.xml',
        'wizard/invoice_analytic_wizard_all_views.xml',
        'wizard/invoice_analytic_wizard_line_views.xml',
    ],
    'qweb': [],
    'images': ['static/description/icon.png'],
    'auto_install': False,
    'installable': True,
}
