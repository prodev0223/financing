# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models


class AccountAnalyticDefault(models.Model):
    _inherit = "account.analytic.default"

    active = fields.Boolean(string='Aktyvus', default=True)
    product_category = fields.Many2one('product.category', string='Produkto Kategorija', ondelete='cascade',
                                       help='Produkto Kategorija')
    account_id = fields.Many2one('account.account', string='Buhalterinė sąskaita')
    invoice_type = fields.Selection([('ins', 'Tiekėjų sąskaitos'),
                                     ('outs', 'Klientų sąskaitos'),
                                     ('all', 'Visos sąskaitos')], string='Sąskaitos tipas', default='all',
                                    required=True)
    journal_id = fields.Many2one('account.journal', string='Žurnalas')
    force_analytic_account = fields.Boolean(string='Teikti pirmenybę')

    @api.multi
    @api.constrains('product_id', 'product_category')
    def _check_category(self):
        for rec in self:
            if rec.product_category and rec.product_id:
                if rec.product_id.categ_id.id != rec.product_category.id:
                    raise exceptions.ValidationError(
                        _("Produkto kategorija neatitinka pasirinkto produkto!\nProdukto %s kategorija yra %s")
                        % (rec.product_id.display_name, rec.product_id.categ_id.name))

    @api.model
    def account_get(self, product_id=None, partner_id=None, user_id=None, date=None,
                    company_id=None, account_id=None, journal_id=None, invoice_type=None):
        domain = []
        if product_id:
            product = self.env['product.product'].browse(product_id)
        else:
            product = self.env['product.product']

        if product_id:
            domain += ['|', ('product_id', '=', product_id)]
        domain += [('product_id', '=', False)]

        if product.categ_id.id:
            domain += ['|', ('product_category', '=', product.categ_id.id)]
        domain += [('product_category', '=', False)]

        if partner_id:
            domain += ['|', ('partner_id', '=', partner_id)]
        domain += [('partner_id', '=', False)]

        if company_id:
            domain += ['|', ('company_id', '=', company_id)]
        domain += [('company_id', '=', False)]

        if user_id:
            domain += ['|', ('user_id', '=', user_id)]
        domain += [('user_id', '=', False)]

        if account_id:
            domain += ['|', ('account_id', '=', account_id)]
        domain += [('account_id', '=', False)]
        if journal_id:
            domain += ['|', ('journal_id', '=', journal_id)]
        domain += [('journal_id', '=', False)]
        if invoice_type:
            searchable = 'ins' if invoice_type in ['in_invoice', 'in_refund'] else 'outs'
            filter_type = 'expense' if invoice_type in ['in_invoice', 'in_refund'] else 'income'
            domain += ['|', ('invoice_type', '=', searchable), ('invoice_type', '=', 'all'),
                       '|', ('analytic_id.account_type', '=', filter_type),
                       ('analytic_id.account_type', '=', 'profit')]
        if date:
            domain += ['|', ('date_start', '<=', date), ('date_start', '=', False)]
            domain += ['|', ('date_stop', '>=', date), ('date_stop', '=', False)]

        best_index = -1
        res = self.env['account.analytic.default']
        for rec in self.search(domain):
            index = 0
            if rec.product_id:
                index += 1
            if rec.product_category:
                index += 0.5
            if rec.partner_id:
                index += 1
            if rec.company_id:
                index += 1
            if rec.user_id:
                index += 1
            if rec.date_start:
                index += 1
            if rec.date_stop:
                index += 1
            if rec.account_id:
                index += 1
            if rec.journal_id:
                index += 1
            if rec.invoice_type in ['ins', 'outs']:
                index += 1
            if index > best_index:
                res = rec
                best_index = index
        return res

    @api.model
    def get_account_ids_to_exclude(self):
        """
        Get all payroll related accounts to exclude when setting analytic default
        :return: A list of account ids to exclude
        """
        company = self.env.user.sudo().company_id
        accounts_to_exclude = self.env['account.account']
        fields_to_exclude_company = ['saskaita_komandiruotes', 'darbdavio_sodra_debit', 'saskaita_debetas',
                                     'saskaita_kreditas', 'saskaita_gpm', 'saskaita_sodra',
                                     'saskaita_komandiruotes_credit', 'atostoginiu_kaupiniai_account_id',
                                     'kiti_atskaitymai_credit', 'employee_advance_account',
                                     'kaupiniai_expense_account_id']
        fields_to_exclude_contract = ['du_debit_account_id', 'sodra_credit_account_id', 'gpm_credit_account_id']
        departments = self.env['hr.department'].sudo().search([])
        contracts = self.env['hr.contract'].sudo().search([])

        for field in fields_to_exclude_company:
            accounts_to_exclude |= departments.mapped(field) + company.mapped(field)
        for field in fields_to_exclude_contract:
            accounts_to_exclude |= contracts.mapped(field)
        salary_rules = self.env['hr.salary.rule'].sudo().search(['&',
                                                                 '|',
                                                                 ('account_debit', '=ilike', '5%'),
                                                                 ('account_debit', '=ilike', '6%'),
                                                                 '|',
                                                                 ('account_credit', '=ilike', '5%'),
                                                                 ('account_credit', '=ilike', '6%')])
        accounts_to_exclude += salary_rules.mapped('account_debit') + salary_rules.mapped('account_credit')
        return accounts_to_exclude.ids
