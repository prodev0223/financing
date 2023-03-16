# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    amount_total_tax_exc_sale_origin = fields.Float(
        string='Suma be PVM (Pardavimo nurodymas)')

    amount_total_tax_inc_sale_origin = fields.Float(
        string='Suma su PVM (Pardavimo nurodymas)')

    cost = fields.Float(
        groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika,robo.group_robo_see_all_incomes')
    gp = fields.Float(
        groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika,robo.group_robo_see_all_incomes')
    gp_percentage = fields.Float(
        groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika,robo.group_robo_see_all_incomes')

    @api.model_cr
    def init(self):
        """
        Init account invoice report view. Add some special columns required by client BROLIS
        :return: None
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE OR REPLACE VIEW account_invoice_report AS (
            SELECT sub.id
                 , sub.id as invoice_line_id
                 , sub.date
                 , sub.product_id
                 , sub.partner_id
                 , sub.country_id
                 , sub.city
                 , sub.analytic_id
                 , sub.analytic_group_id
                 , sub.department_id
                 , sub.payment_term_id
                 , sub.uom_name
                 , sub.currency_id
                 , sub.journal_id
                 , sub.fiscal_position_id
                 , sub.user_id
                 , sub.company_id
                 , sub.nbr
                 , sub.type
                 , sub.amount_total_tax_exc_sale_origin
                 , sub.amount_total_tax_inc_sale_origin
                 , sub.state
                 , sub.weight
                 , sub.volume
                 , sub.categ_id
                 , sub.supplier_id
                 , sub.date_due
                 , sub.account_id
                 , sub.account_line_id
                 , sub.partner_bank_id
                 , sub.product_qty
                 , sub.price_total                          AS price_total
                 , sub.price_average                        AS price_average
                 , 1                                        AS currency_rate
                 , sub.residual                             AS residual
                 , sub.commercial_partner_id                AS commercial_partner_id
                 , sub.team_id                              AS team_id
                 , sub.amount_currency_untaxed_signed
                 , sub.date_due_report                      AS date_due_report
                 , sub.amount_with_tax
                 , sub.amount_with_tax - sub.price_total    AS amount_tax
                 , sub.amount_currency_with_tax
                 , sub.gp
                 , sub.gp_percentage
                 , sub.cost
                 , sub.gp_invoice_date
                 , sub.cost_invoice_date
                 , sub.invoice_id
                 , sub.markup_price_percentage
                 , sub.no_stock_moves
                 , sub.partner_category_id
                 , sub.ap_employee_id
                 , sub.submitted
                 , sub.create_date
                 , sub.tax_code
                 , sub.secondary_tax_code
            FROM (
                SELECT ail.id AS id
                     , ai.date_invoice AS date
                     , ail.product_id
                     , ai.ap_employee_id
                     , ai.partner_id
                     , ai.payment_term_id
                     , ail.account_analytic_id AS analytic_id
                     , aa.analytic_group_id
                     , hr_department.id AS department_id
                     , u2.name AS uom_name
                     , ai.currency_id
                     , ai.journal_id
                     , ai.fiscal_position_id
                     , ai.user_id
                     , ai.company_id
                     , 1 AS nbr
                     , ai.type
                     , ai.state
                     , ai.submitted
                     , pt.categ_id
                     , pt.supplier_id
                     , ai.date_due
                     , ai.account_id
                     , ail.account_id AS account_line_id
                     , ail.amount_total_tax_exc_sale_origin
                     , ail.amount_total_tax_inc_sale_origin
                     , ai.partner_bank_id
                     , SUM ((invoice_type.sign * ail.quantity) / (u.factor * u2.factor)) AS product_qty
                     , SUM(ABS(ail.price_subtotal_signed)) / 
                       (CASE WHEN SUM(ail.quantity / u.factor * u2.factor) <> 0::numeric
                       THEN SUM(ail.quantity / u.factor * u2.factor)
                       ELSE 1::numeric END)
                        AS price_average
                     , (CASE WHEN ai.type IN ('out_invoice', 'in_invoice')
                             THEN ai.residual_company_signed
                             ELSE -ai.residual_company_signed
                        END) / invoice_line_count.n_lines * COUNT(*) * invoice_type.sign
                        AS residual
                     , ai.commercial_partner_id AS commercial_partner_id
                     , partner.country_id
                     , partner.city
                     , SUM(pr.weight * (invoice_type.sign * ail.quantity) / u.factor * u2.factor) AS weight
                     , SUM(pr.volume * (invoice_type.sign * ail.quantity) / u.factor * u2.factor) AS volume
                     , ai.team_id AS team_id
                     , ai.date_due_report AS date_due_report
                    -- account_invoice_line.price_subtotal, account_move_line.total_with_tax_amount 
                    -- and account_move_line.total_with_tax_amount_company are always positive.
                    -- we want them negative when in in_invoice or out_refund for reports:
                     , SUM(CASE WHEN ai.type IN ('in_invoice', 'out_refund')
                                THEN -ail.price_subtotal
                                ELSE ail.price_subtotal
                           END) AS amount_currency_untaxed_signed
                     , SUM(CASE WHEN ai.type IN ('in_invoice', 'out_refund')
                                THEN -ail.total_with_tax_amount
                                ELSE ail.total_with_tax_amount
                           END) AS amount_currency_with_tax
                     , SUM(CASE WHEN ai.type IN ('in_invoice', 'out_refund')
                                THEN -ail.total_with_tax_amount_company
                                ELSE ail.total_with_tax_amount_company
                           END) AS amount_with_tax
                    -- account_invoice_line.price_subtotal_signed 
                    -- is positive when in {in,out}_invoice and negative when in {in,out}_refund
                    -- we want it positive in in_refund and out_invoice, negative in in_invoice and out_refund
                    -- so we have to change sign when in  in_invoice and in_refund
                     , SUM(CASE WHEN ai.type IN ('in_invoice', 'in_refund')
                                THEN -ail.price_subtotal_signed
                                ELSE ail.price_subtotal_signed
                           END) AS price_total
                     , SUM(ail.gp) AS gp
                     , SUM(ail.gp_invoice_date) AS gp_invoice_date
                     , SUM(ail.gp) / NULLIF(sum(ail.price_subtotal_signed), 0.0) * 100.0 AS gp_percentage
                     , SUM(ail.cost) AS cost
                     , SUM(ail.gp) / NULLIF(sum(ail.cost), 0.0) * 100.0 AS markup_price_percentage
                     , SUM(ail.cost_invoice_date) AS cost_invoice_date
                     , ai.id AS invoice_id
                     , bool_or(ail.no_stock_moves) AS no_stock_moves
                     , partner.partner_category_id
                     , ai.create_date
                     , tc.code1 AS tax_code
                     , tc.code2 AS secondary_tax_code
                FROM account_invoice_line ail
                JOIN account_invoice ai
                        ON ai.id = ail.invoice_id
                JOIN res_partner partner
                        ON ai.commercial_partner_id = partner.id
                LEFT JOIN product_product pr
                        ON pr.id = ail.product_id
                LEFT JOIN product_template pt
                        ON pt.id = pr.product_tmpl_id
                LEFT JOIN product_uom u
                        ON u.id = ail.uom_id
                LEFT JOIN product_uom u2
                        ON u2.id = pt.uom_id
                LEFT JOIN res_users
                        ON ai.user_id = res_users.id
                LEFT JOIN (
                            SELECT a.id
                                 , a.code1
                                 , a.code2 FROM (
                                      SELECT ailt1.invoice_line_id AS id
                                           , ailt1.tax_id AS tax1
                                           , at1.code  AS code1
                                           , ailt2.tax_id AS tax2
                                           , at2.code AS code2
                                      FROM account_invoice_line_tax ailt1
                                      LEFT JOIN account_invoice_line_tax ailt2
                                              ON ailt2.invoice_line_id = ailt1.invoice_line_id AND ailt1.tax_id != ailt2.tax_id
                                      LEFT JOIN account_tax at1
                                              ON at1.id = ailt1.tax_id AND at1.code LIKE '%PVM%'
                                      LEFT JOIN account_tax at2
                                              ON at2.id = ailt2.tax_id AND at2.code NOT LIKE '%PVM%'
                                      GROUP BY ailt1.invoice_line_id, at1.code , at2.code, ailt1.tax_id, ailt2.tax_id
                                      ORDER BY ailt1.invoice_line_id DESC 
                                      ) AS a
                            WHERE a.tax1 IS NOT NULL AND a.code1 IS NOT NULL
                               OR tax1 IS NULL) tc
                        ON tc.id = ail.id
                LEFT JOIN res_partner user_partner
                        ON user_partner.id = res_users.partner_id
                LEFT JOIN (
                            SELECT DISTINCT ON (emp.address_home_id) *
                                FROM (
                                    SELECT emp.id AS e_id
                                         , emp.address_home_id
                                         , emp.department_id
                                         , rr.active
                                    FROM hr_employee emp
                                    JOIN resource_resource rr
                                            ON rr.id = emp.resource_id) emp
                            ORDER BY emp.address_home_id, active desc, department_id desc, e_id desc) emp
                        ON emp.address_home_id = user_partner.id
                LEFT JOIN hr_employee ap
                        ON ap.id = ai.ap_employee_id
                LEFT JOIN hr_department
                        ON emp.department_id = hr_department.id
                LEFT JOIN account_analytic_account aa
                        ON ail.account_analytic_id = aa.id
                JOIN (
                    -- Temporary table to decide if the qty should be added or retrieved (Invoice vs Refund) 
                    SELECT id
                         , (CASE WHEN ai.type::text = ANY 
                           (ARRAY['out_refund'::character varying::text, 'in_invoice'::character varying::text])
                                 THEN -1
                                 ELSE 1
                            END) AS sign
                    FROM account_invoice ai
                    ) AS invoice_type
                        ON invoice_type.id = ai.id
                JOIN (
                    -- Temporary table to store invoice line count per invoice
                    SELECT COUNT(id) as n_lines
                         , invoice_id
                    FROM account_invoice_line
                    GROUP BY invoice_id
                    ) AS invoice_line_count
                        ON invoice_line_count.invoice_id = ai.id

                GROUP BY ail.id, ail.product_id, ai.ap_employee_id, ail.account_analytic_id, ai.date_invoice, ai.id,
                    ai.partner_id, ai.payment_term_id, u2.name, u2.id, ai.currency_id, ai.journal_id,
                    ai.fiscal_position_id, ai.user_id, ai.company_id, ai.type, invoice_type.sign, ai.state, pt.categ_id,
                    pt.supplier_id, ai.date_due, ai.account_id, ail.account_id, ai.partner_bank_id, ai.residual_company_signed,
                    ai.amount_total_company_signed, ai.commercial_partner_id, partner.country_id, partner.city,
                    ai.team_id, partner.partner_category_id, hr_department.id, ai.create_date, 
                    ail.amount_total_tax_exc_sale_origin, ail.amount_total_tax_inc_sale_origin,
                    tax_code, aa.analytic_group_id, secondary_tax_code, invoice_line_count.n_lines
                
            ) AS sub
        )""")


AccountInvoiceReport()
