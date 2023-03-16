# -*- encoding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name': 'Lithuanian - Accounting - Payroll',
    'version': '1.0',
    'author': 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'category': 'Localization/Account Charts',
    'description': """
This is the module to manage the payroll for Lithuania.
==================================================================================
    """,
    'depends': ['l10n_lt', 'hr_payroll_account',
                'calendar', 'mail', 'account_cancel', 'document', 'robo_core'],
    'demo': [],
    'data': ['data/l10n_lt_hr_payroll_data.xml',
             'data/seimynine_padetis.xml',
             'data/darbuotojo_darbingumas.xml',
             # 'data/resource.calendar.csv',
             # 'data/resource.calendar.attendance.csv',
             'data/ir.sequence.csv',
             'data/account.journal.csv',
             'data/country.allowance.csv',
             'data/country.allowance.line.csv',
             # 'data/setup.xml',#
             'data/a.klase.kodas.csv',
             'data/b.klase.kodas.csv',
             'data/payroll_parameters.xml',
             'data/state_declared_emergency.xml',
             'data/ir_cron.xml',
             'data/ir_sequence.xml',
             'data/mail_channel.xml',
             'view/payroll.xml',
             'view/darbuotojai_view.xml',  #
             'view/hr_employee_kind_periodic_views.xml',  #
             'view/pastas_view.xml',  #
             'view/algalapis.xml',  #
             'view/automatic_payroll.xml',  #
             'view/iseigines_view.xml',  #
             'view/avansas_view.xml',
             'view/payroll_settings_view.xml',  #
             'view/holidays_view.xml',
             'view/ziniarastis_view.xml',
             'view/appointments_view.xml',
             'view/atostoginiai_view.xml',
             'view/payroll_dashboard.xml',  #
             'view/vdu_view.xml',
             'view/atostoginiai_report_view.xml',
             'view/allowance_view.xml',
             'view/leaves_report_wizard_view.xml',
             'view/executive_deduction_order.xml',
             'view/hr_employee_downtime_views.xml',
             'view/hr_contract_views.xml',
             'view/hr_employee_bonus_periodic_views.xml',
             'view/hr_employee_compensation_views.xml',
             'view/hr_employee_holiday_accumulation_views.xml',
             'view/hr_employee_holiday_usage_line_views.xml',
             'view/hr_employee_holiday_usage_views.xml',
             'view/hr_employee_overtime_views.xml',
             'view/hr_employee_holiday_compensation_views.xml',
             'view/hr_employee_forced_work_time_views.xml',

             'security/ir.model.access.csv',
             'security/record.rules.xml',
             'data/tabelio.zymejimas.csv',
             'data/hr.holidays.status.csv',
             'data/sistema.iseigines.csv',
             'report_qweb/assets.xml',
             'report_qweb/algalapis.xml',
             'report_qweb/algalapis_israsas.xml',
             'report_qweb/algalapio_israso_email.xml',
             'report_qweb/suvestine.xml',
             'report_qweb/islaidos.xml',
             'report_qweb/atostogu_suvestine.xml',
             'report_qweb/report_atostogu_suvestine.xml',
             'report_qweb/report_employee_salary.xml',
             'report_qweb/vdu.xml',
             'report/hr_payslip_run_reports.xml',
             'report/hr_payslip_run_templates.xml',
             'report/hr_employee_work_norm_report_views.xml',
             'report/atostoginiu_kaupiniu_report_views.xml',

             'view/schedule_template_views.xml',
             'wizard/default_schedule_template_setter_views.xml',
             'wizard/hr_payslip_export_views.xml',
             'wizard/hr_payslip_run_payslip_print_views.xml',
             'wizard/ziniarastis_period_selected_export_views.xml',
             'wizard/hr_contract_appointment_create_views.xml',
             'wizard/hr_contract_create_views.xml',
             'wizard/payslip_print_language_wizard_views.xml',
             'wizard/vdu_report_views.xml',
             'wizard/downtime_report_views.xml',
             'wizard/hr_employee_work_norm_report_export_views.xml',
             'wizard/atostoginiu_kaupiniu_wizard_views.xml',
             ],
    'qweb': [
        'static/src/xml/ziniarastis.xml',
        'static/src/xml/popup.xml',
        'static/src/xml/ziniarastis_view.xml',
    ],
    'auto_install': False,
    'installable': True,
}
