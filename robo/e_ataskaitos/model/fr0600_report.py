# -*- coding: utf-8 -*-


from odoo import api, fields, models, tools


class Fr0600Report(models.Model):
    _name = 'fr0600.report'
    _auto = False
    _rec_name = 'date'

    date = fields.Date(string='Data',
                       groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    invoice_id = fields.Many2one('account.invoice', string='Invoice',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    account_id = fields.Many2one('account.account', string='Account',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    tax_account_id = fields.Many2one('account.account', string='Tax Account',
                                 groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    code = fields.Char(string='Code', groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')

    amount = fields.Float(string='amount', sequence=1,
                               groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user')
    inv_type = fields.Selection([
        ('out_invoice', 'Klientinė sąskaita'),
        ('in_invoice', 'Tiekėjo sąskaita'),
        ('out_refund', 'Kreditinė sąskaita'),
        ('in_refund', 'Grąžinimai tiekėjams'),
    ], groups='robo_basic.group_robo_free_employee,robo_basic.group_robo_premium_user', string='Sąskaitos tipas')
    skip_isaf = fields.Boolean(string='Praleisti ISAF')
    matching_account = fields.Boolean(string='Account matches tax account')
    included_in_report = fields.Boolean()
    part = fields.Selection([('first', 'First'), ('second', 'Second')], string='Part (Technical field)')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self._cr.execute('''
        CREATE OR REPLACE VIEW fr0600_report AS 
        SELECT *
            , CASE WHEN tax_account_id = account_id THEN true ELSE false END AS matching_account  
        FROM (
 
        (
            SELECT account_account_tag.code as code
                 , account_move_line.balance as amount
                 , account_invoice.type as inv_type
                 , account_move_line.id
                 , account_move_line.date as date
                 , account_move_line.account_id as account_id
                 , account_tax.account_id as tax_account_id
                 , account_invoice.id as invoice_id
                 , account_invoice.skip_isaf
                 , CASE WHEN (
                                account_invoice.skip_isaf = true 
                                AND account_move_line.account_id = account_tax.account_id           
                                OR account_invoice.skip_isaf = false           
                                OR account_invoice.skip_isaf IS NULL
                             )
                        THEN TRUE
                        ELSE FALSE END AS included_in_report
                , 'first' as part
            FROM
                account_move_line         
            JOIN
                account_move 
                    ON account_move_line.move_id = account_move.id         
            JOIN
                account_tax 
                    ON account_tax.id = account_move_line.tax_line_id         
            JOIN
                account_tax_account_tag 
                    ON account_tax.id = account_tax_account_tag.account_tax_id         
            JOIN
                account_account_tag 
                    ON account_account_tag.id = account_tax_account_tag.account_account_tag_id         
            LEFT JOIN
                account_invoice 
                    ON account_move_line.invoice_id = account_invoice.id         
            WHERE
                account_move.state = 'posted' 
                AND (
                    account_account_tag.base is null
                    OR account_account_tag.base = FALSE
                )                
        ) 
        
        UNION ALL
        (
            SELECT account_account_tag.code as code
                 , account_move_line.balance as amount
                 , account_invoice.type as inv_type
                 , account_move_line.id
                 , account_move_line.date as date
                 , account_move_line.account_id as account_id
                 , account_tax.account_id as tax_account_id
                 , account_invoice.id as invoice_id
                 , account_invoice.skip_isaf
                 , COALESCE(account_account_tag.base, FALSE) AS included_in_report
                 , 'second' AS part
            FROM
                account_move_line         
            JOIN
                account_move 
                    ON account_move_line.move_id = account_move.id         
            JOIN
                account_move_line_account_tax_rel 
                    ON account_move_line_account_tax_rel.account_move_line_id = account_move_line.id         
            JOIN
                account_tax 
                    ON account_move_line_account_tax_rel.account_tax_id = account_tax.id         
            JOIN
                account_tax_account_tag 
                    ON account_tax.id = account_tax_account_tag.account_tax_id         
            JOIN
                account_account_tag 
                    ON account_account_tag.id = account_tax_account_tag.account_account_tag_id         
            LEFT JOIN
                account_invoice 
                    ON account_move_line.invoice_id = account_invoice.id         
            WHERE
                account_move.state = 'posted'  
        ) ) as foo
        ''')

    # @api.model
    # def refresh_view(self):
    #     if super(Fr0600Report, self).refresh_view():
    #         self._cr.execute('REFRESH VIEW fr0600_report')