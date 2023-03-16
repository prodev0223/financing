# -*- coding: utf-8 -*-


from odoo import fields, models, tools


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'
    _auto = False

    invoice_line_id = fields.Many2one('account.invoice.line', string='Sąskaitos eilutė', sequence=100)
    analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                  lt_string='Analitinė sąskaita', sequence=10)
    date = fields.Date(string='Data',
                       groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    product_id = fields.Many2one('product.product', string='Produktas',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    product_qty = fields.Float(string='Kiekis', sequence=3,
                               groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    uom_name = fields.Char(string='Matavimo vienetas',
                           groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    payment_term_id = fields.Many2one('account.payment.term', string='Mokėjimo terminas',
                                      groups='robo_basic.group_robo_premium_accountant')
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiskalinė pozicija',
                                         groups='robo_basic.group_robo_premium_accountant')
    currency_id = fields.Many2one('res.currency', string='Valiuta',
                                  groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    categ_id = fields.Many2one('product.category', string='Produkto kategorija',
                               groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    journal_id = fields.Many2one('account.journal', string='Žurnalas',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    partner_id = fields.Many2one('res.partner', string='Partneris',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    supplier_id = fields.Many2one('res.partner', string='Tiekėjas',
                                  groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    commercial_partner_id = fields.Many2one('res.partner', string='Partnerio kompanija', help="Juridinis asmuo",
                                            groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    company_id = fields.Many2one('res.company', string='Kompanija',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    user_id = fields.Many2one('res.users', string='Pardavėjas',
                              groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    price_total = fields.Float(string='Suma be mokesčių', sequence=1,
                               groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    user_currency_price_total = fields.Float(string="Suma be mokesčių",
                                             groups='robo_basic.group_robo_premium_accountant')
    price_average = fields.Float(string='Vidutinė kaina', groups='robo_basic.group_robo_premium_manager')
    user_currency_price_average = fields.Float(string="Vidutinė kaina",
                                               groups='robo_basic.group_robo_premium_accountant')
    currency_rate = fields.Float(string='Valiutų kursas',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user',
                                 sequence=105)
    nbr = fields.Integer(string='# eilučių', sequence=99,
                         groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    type = fields.Selection([
        ('out_invoice', 'Klientinė sąskaita'),
        ('in_invoice', 'Tiekėjo sąskaita'),
        ('out_refund', 'Kreditinė sąskaita'),
        ('in_refund', 'Grąžinimai tiekėjams'),
    ], groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user', string='Sąskaitos tipas')
    state = fields.Selection([
        ('draft', 'Nepatvirtinta'),
        ('proforma', 'Išankstinė'),
        ('proforma2', 'Išankstinė'),
        ('open', 'Patvirtinta'),
        ('paid', 'Apmokėta'),
        ('cancel', 'Atšaukta')
    ], string='Būsena', groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    date_due = fields.Date(string='Mokėjimo terminas',
                           groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user', sequence=11)
    account_id = fields.Many2one('account.account', string='Buhalterinė sąskaita',
                                 groups='robo_basic.group_robo_premium_manager')
    account_line_id = fields.Many2one('account.account', string='Operacijų sąskaita',
                                      groups='robo_basic.group_robo_premium_manager')
    partner_bank_id = fields.Many2one('res.partner.bank', string='Banko sąskaita',
                                      groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    residual = fields.Float(string='Liko mokėti', sequence=4,
                            groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    user_currency_residual = fields.Float(string="Liko mokėti", groups='robo_basic.group_robo_premium_accountant')
    country_id = fields.Many2one('res.country', string='Partnerio valstybė',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    city = fields.Char(string='Partnerio miestas',
                       groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    weight = fields.Float(string='Svoris', groups='robo_basic.group_robo_premium_manager')
    volume = fields.Float(string='Tūris', groups='robo_basic.group_robo_premium_manager')
    cost = fields.Float(string='Savikaina', sequence=5,
                        groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    gp = fields.Float(string='Pelno marža', sequence=6,
                      groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    cost_invoice_date = fields.Float(string='Savikaina sąskaitos data', sequence=5,
                                     groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    gp_invoice_date = fields.Float(string='Pelno marža sąskaitos data', sequence=6,
                                   groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    gp_percentage = fields.Float(string='Pelno marža (%)', group_operator='price_total', digits=(0, 0), sequence=7,
                                 groups='robo_basic.group_robo_premium_manager,robo.group_menu_kita_analitika')
    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    amount_currency_with_tax = fields.Float(string='Užsienio valiuta su mokesčiais', sequence=9)
    amount_currency_untaxed_signed = fields.Float(string='Užsienio valiuta be mokesčių', sequence=9,
                                                  groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    partner_category_id = fields.Many2one('partner.category', string='Partnerio kategorija', sequence=10)
    date_due_report = fields.Date(string='Perderėtas apmokėjimo terminas',
                                  groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user',
                                  sequence=12)
    team_id = fields.Many2one('crm.team', string='Pardavimų komanda')
    amount_tax = fields.Float(string='PVM suma', sequence=2,
                              groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    amount_with_tax = fields.Float(string='Suma su mokesčiais', sequence=2)
    department_id = fields.Many2one('hr.department', string='Padalinys', lt_string='Padalinys')
    markup_price_percentage = fields.Float(string='Antkainis (%)', sequence=8, group_operator='cost')
    no_stock_moves = fields.Boolean(string='Nėra susijusių sandėlio judėjimų',
                                    lt_string='Nėra susijusių sandėlio judėjimų')
    ap_employee_id = fields.Many2one('hr.employee', string='Atskaitingas asmuo')
    submitted = fields.Char(string='Pateikęs asmuo')
    create_date = fields.Datetime(string='Sukūrimo data')
    tax_code = fields.Char(string='PVM kodas')
    secondary_tax_code = fields.Char(string='PVM kodas (antrinis)')
    analytic_group_id = fields.Many2one('account.analytic.group', string='Analitinė grupė')

    def init(self):
        # tools.drop_view_if_exists(self.env.cr, self._table)
        create = False
        new_cr = self.pool.cursor()
        try:
            new_cr.execute('''SELECT analytic_id FROM account_invoice_report LIMIT 1''')
        except:
            create = True
        finally:
            new_cr.rollback()
            new_cr.close()
        if create:
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
                     , ai.partner_bank_id
                     , SUM ((invoice_type.sign * ail.quantity) / (u.factor * u2.factor)) AS product_qty
                     , SUM(ABS(ail.price_subtotal_signed)) / (CASE WHEN SUM(ail.quantity / u.factor * u2.factor) <> 0::numeric
                                                                   THEN SUM(ail.quantity / u.factor * u2.factor)
                                                                   ELSE 1::numeric
                                                            END)
                        AS price_average
                     , (CASE WHEN ai.type IN ('out_invoice', 'in_invoice')
                             THEN ai.residual_company_signed
                             ELSE -ai.residual_company_signed
                        END) / invoice_line_count.n_lines * count(*) * invoice_type.sign
                        AS residual
                     , ai.commercial_partner_id AS commercial_partner_id
                     , partner.country_id
                     , partner.city
                     , SUM(pr.weight * (invoice_type.sign * ail.quantity) / u.factor * u2.factor) AS weight
                     , SUM(pr.volume * (invoice_type.sign * ail.quantity) / u.factor * u2.factor) AS volume
                     , ai.team_id AS team_id
                     , ai.date_due_report AS date_due_report
                    -- account_invoice_line.price_subtotal, account_move_line.total_with_tax_amount and account_move_line.total_with_tax_amount_company are always positive.
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
                    -- account_invoice_line.price_subtotal_signed is positive when in {in,out}_invoice and negative when in {in,out}_refund
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
                         , (CASE WHEN ai.type::text = ANY (ARRAY['out_refund'::character varying::text, 'in_invoice'::character varying::text])
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
                    pt.supplier_id, ai.date_due, ai.account_id, ail.account_id, ai.partner_bank_id, 
                    ai.residual_company_signed, ai.amount_total_company_signed, ai.commercial_partner_id, 
                    partner.country_id, partner.city, ai.team_id, partner.partner_category_id, hr_department.id, 
                    ai.create_date, tax_code, aa.analytic_group_id, secondary_tax_code, invoice_line_count.n_lines
        
            ) AS sub
        )""")
