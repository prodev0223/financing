# SCRIPT USED TO PARTIALLY CLEAN A DEEPER DB
# NOT COMPLETE, E.G USERS ARE NOT DELETED
# MOSTLY CLEAN EMPLOYEE WAGES, SLIPS HOLIDAYS ETC AND ALL ACCOUNTING ENTRIES AND SALES / INVOICES
# MOST LIKELY BREAKS ON ROBO DB


# WARNING: CAN RUN FOR A VERY LONG TIME (MAYBE MORE REQUESTS WOULD MAKE IT FASTER BY REMOVING SOME CHECKS)

env.cr.execute("""
DELETE FROM account_partial_reconcile;
DELETE FROM account_full_reconcile;
DELETE FROM account_move_line;
DELETE FROM account_bank_statement_line;
DELETE FROM account_bank_statement;
DELETE FROM account_date_fix;
DELETE FROM account_invoice_line;
DELETE FROM account_invoice;
DELETE FROM account_move;
DELETE FROM account_analytic_line;
DELETE FROM hr_payslip;
DELETE FROM hr_payslip_worked_days;
DELETE FROM e_document;
UPDATE hr_contract_appointment SET wage = 0;
UPDATE hr_contract SET wage = 0;
DELETE FROM hr_holidays_payment_line;
DELETE FROM hr_holidays;
DELETE FROM sale_order_line;
DELETE FROM sale_bundle_line;
DELETE FROM sale_order;
DELETE FROM hr_employee_bonus;
DELETE FROM hr_employee_natura;
DELETE FROM hr_employee_isskaitos;
DELETE FROM hr_expense;
DELETE FROM hr_employee_payment;
DELETE FROM darbo_avansas;
DELETE FROM avansai_run;
DELETE FROM ziniarastis_period;
DELETE FROM employee_vdu;
DELETE FROM sale_planning_line_change;
DELETE FROM sale_planning_line;
DELETE FROM account_asset_responsible;
DELETE FROM account_asset_change_line;
DELETE FROM account_asset_revaluation_history;
DELETE FROM account_asset_asset;
DELETE FROM res_partner WHERE id NOT IN (SELECT partner_id FROM res_users UNION SELECT partner_id FROM purchase_order UNION SELECT partner_id FROM delivery_carrier UNION SELECT address_home_id FROM hr_employee);
""")