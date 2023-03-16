# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, _, api, exceptions, tools


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _default_account_id(self):
        return self.env['account.account'].search([('code', '=', '652')], limit=1)

    non_deductible_account_id = fields.Many2one('account.account', string='Neleidžiami atskaitymai',
                                                default=_default_account_id)
    vat_account_ids = fields.Many2many('account.account', 'company_account_vat_rel', string='Pvm sąskaitos',
                                       help='Sąskaitos PVM sudengimui')
    import_vat_account_ids = fields.Many2many('account.account', 'company_account_vat_import_rel',
                                              string='Importo PVM sąskaitos',
                                              help='Sąskaitos importo PVM sudengimui')
    vat_account_id = fields.Many2one('account.account', string='Mokėtino PVM sąskaita')
    import_vat_account_id = fields.Many2one('account.account', string='Mokėtino importo PVM sąskaita')
    vat_journal_id = fields.Many2one('account.journal', string='PVM žurnalas')
    auto_lock_day_non_advisers = fields.Integer(string='DK įrašų užrakinimo diena ne buhalteriams', default=0)
    auto_lock_day_advisers = fields.Integer(string='DK įrašų užrakinimo diena buhalteriams', default=0)
    auto_lock_day = fields.Integer(string='DK įrašų užrakinimo diena', default=0)
    cashier_id = fields.Many2one('hr.employee', string='Kasininkas',
                                 help='Kasos orderiuose nurodomas kasininkas')
    cashier_manager_id = fields.Many2one('hr.employee', string='Kasininko vadovas',
                                         help='Kasos orderius patvirtinantis asmuo')
    cashier_accountant_id = fields.Many2one('res.partner', string='Vyr. buhalteris (buhalteris)',
                                            help='Kasos orderius patvirtinantis asmuo',
                                            domain="[('is_company','=',False)]")
    period_close_journal_id = fields.Many2one('account.journal', string='Periodo uždarymo žurnalas')
    cash_receipt_journal_id = fields.Many2one('account.journal', string='Pinigų kvitų žurnalas')
    invoice_vat_printing_method = fields.Selection(string="Sąskaitų su PVM spausdinimo metodas", required=True,
                                                   selection=[('B2B', 'B2B'), ('B2C', 'B2C')], default='B2B')
    rounding_expense = fields.Many2one('account.account', string='Rounding Expense Account')
    rounding_income = fields.Many2one('account.account', string='Rounding Income Account')
    vat_status_ids = fields.One2many('res.company.vat.status', 'company_id')
    vat_payer = fields.Boolean(compute='get_vat_payer_status')
    accountant_lock_date = fields.Date(string="Lock Date for Accountants",
                                       help="Only chief accountants will be able to edit accounts prior to and inclusive of this date.")
    tax_calculation_rounding_method = fields.Selection([
        ('round_per_line', 'Round per Line'),
        ('round_globally', 'Round Globally'),
    ], default='round_globally')
    inv_due_date_edit = fields.Boolean(string='Keisti sąskaitose apmokėjimo datą')


    @api.one
    @api.depends('vat_status_ids.date_from', 'vat_status_ids.date_to', 'vat')
    def get_vat_payer_status(self):
        if self.vat_status_ids:
            date = self._context.get('date', False)
            if not date:
                date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for s in self.vat_status_ids:
                if not (s.date_from and date < s.date_from or s.date_to and date > s.date_to):
                    self.vat_payer = True
                    return
        else:
            #  keep consistent with previous behaviour : if no status lines, just check the existence of code
            if self.vat:
                self.vat_payer = True

    @api.one
    def set_default_accounts(self):
        if not self.env.user._is_admin():
            raise exceptions.Warning(_('Only administrator can change these settings'))
        ir_values_obj = self.env['ir.values']
        default_ra_id = self.env['account.account'].search([('code', '=', '2410'), ('company_id', '=', self.id)],
                                                           limit=1)
        default_pa_id = self.env['account.account'].search([('code', '=', '4430'), ('company_id', '=', self.id)],
                                                           limit=1)
        if default_ra_id:
            ir_values_obj.sudo().set_default('res.partner', "property_account_receivable_id", default_ra_id.id,
                                             for_all_users=True, company_id=self.id)
        if default_pa_id:
            ir_values_obj.sudo().set_default('res.partner', "property_account_payable_id", default_pa_id.id,
                                             for_all_users=True, company_id=self.id)
        if not self.income_currency_exchange_account_id:
            income_currency_exchange_account_id = self.env['account.account'].search([('code', '=', '5803'),
                                                                                      ('company_id', '=', self.id)],
                                                                                     limit=1)
            if income_currency_exchange_account_id:
                self.income_currency_exchange_account_id = income_currency_exchange_account_id
        if not self.expense_currency_exchange_account_id:
            expense_currency_exchange_account_id = self.env['account.account'].search([('code', '=', '6803'),
                                                                                       ('company_id', '=', self.id)],
                                                                                      limit=1)
            if expense_currency_exchange_account_id:
                self.expense_currency_exchange_account_id = expense_currency_exchange_account_id

    @api.one
    def set_default_taxes(self):
        if not self.env.user._is_admin():
            raise exceptions.Warning(_('Only administrator can change these settings'))
        ir_values_obj = self.env['ir.values']
        default_sale_tax_id = self.env['account.account'].with_context(lang='lt_LT').search(
            [('name', '=', 'Pardavimas Šalies Teritorijoje (21%)'),
             ('company_id', '=', self.id)], limit=1)  # todo
        default_purchase_tax_id = self.env['account.account'].with_context(lang='lt_LT').search(
            [('name', '=', 'Pirkimas Šalies Teritorijoje (21%) - Atskaitoma'),
             ('company_id', '=', self.id)], limit=1)  # todo
        if default_sale_tax_id:
            ir_values_obj.sudo().set_default('product.template', "taxes_id", [default_sale_tax_id.id],
                                             for_all_users=True, company_id=self.id)
        if default_purchase_tax_id:
            ir_values_obj.sudo().set_default('product.template', "supplier_taxes_id", [default_purchase_tax_id.id],
                                             for_all_users=True, company_id=self.id)

    @api.one
    def set_default_vat_accounts(self):
        account_obj = self.env['account.account']
        if not self.vat_account_id:
            vat_account = account_obj.search([('company_id', '=', self.id), ('code', '=', 44924)], limit=1)
            if vat_account:
                self.vat_account_id = vat_account.id
        if not self.import_vat_account_id:
            import_vat_account_id = account_obj.search([('company_id', '=', self.id), ('code', '=', 44925)], limit=1)
            if import_vat_account_id:
                self.import_vat_account_id = import_vat_account_id.id
        if not self.vat_account_ids:
            vat_account_ids = account_obj.search(
                [('company_id', '=', self.id), ('code', 'in', [44921, 24411, 24413, 24411])]).ids
            if vat_account_ids:
                self.vat_account_ids = [(6, 0, vat_account_ids)]
        if not self.import_vat_account_ids:
            import_vat_account_ids = account_obj.search(
                [('company_id', '=', self.id), ('code', 'in', [44923, 24412])]).ids
            if import_vat_account_ids:
                self.import_vat_account_ids = [(6, 0, import_vat_account_ids)]
        if not self.vat_journal_id:
            journal = self.env['account.journal'].search([('code', '=', 'PVM'), ('company_id', '=', self.id)], limit=1)
            if not journal:
                journal = self.env['account.journal'].create({
                    'code': 'PVM',
                    'type': 'general',
                    'name': 'PVM žurnalas',
                    'company_id': self.id,
                    'show_on_dashboard': False,
                })
            self.vat_journal_id = journal.id

    def reflect_code_digits_change(self, digits):
        pass

    # Lock Dates // ---------------------------------------------------------------------------------------------------

    @api.model
    def get_user_accounting_lock_date(self):
        """
        Get the lock date -- if user is an accountant select the max date between
        fiscal-year and accounting lock date, otherwise max date between
        fiscal-year and period lock date
        :return: lock date based on the user
        """
        company = self.sudo().env.user.company_id
        constraining_lock_dates = [company.fiscalyear_lock_date]

        # If user is an accountant, add accounting lock date to the list
        # otherwise, period lock date
        if self.user_has_groups('account.group_account_manager'):
            constraining_lock_dates.append(company.accountant_lock_date)
        else:
            constraining_lock_dates.append(company.period_lock_date)

        # Select the max date between fiscal-year and other added date
        return max(constraining_lock_dates)

    @api.model
    def accounting_lock_error_message(self, lock_date):
        """
        Format and return lock date error message based on the user
        :param lock_date: accounting lock date
        :return: error message
        """
        message = _('Negalite pridėti/koreguoti įrašų ankstesnių nei užrakinimo data {0}.').format(lock_date)
        if self.user_has_groups('account.group_account_manager'):
            message += _(' Kreipkitės į vyr. buhalterį')
        return message

    @api.multi
    def check_locked_accounting(self, date):
        """
        Check whether passed date is in locked period
        :param date: date to check against the lock date
        :return: True if date is locked otherwise False
        """
        self.ensure_one()
        lock_date = self.get_user_accounting_lock_date()
        return date <= lock_date

    @api.model
    def check_date_overlap(self, line_to_check):
        date_to = line_to_check.date_to
        date_from = line_to_check.date_from
        for line in self.vat_status_ids.filtered(lambda l: l.id != line_to_check.id):
            if date_to:
                if not (line.date_from and date_to < line.date_from or line.date_to and date_to > line.date_to):
                    return True
            if date_from:
                if not (line.date_from and date_from < line.date_from or line.date_to and date_from > line.date_to):
                    return True
            if not date_to and date_from:
                if line.date_from and line.date_from > date_from:
                    return True
            if not date_from and date_to:
                if line.date_to and line.date_to < date_to:
                    return True
        return False

    @api.model
    def cron_change_lock_date(self):
        accountant_lock_date = datetime.utcnow() - relativedelta(months=3, day=31)
        non_accountant_lock_date = datetime.utcnow() - relativedelta(months=2, day=31)
        for company in self.env['res.company'].search([]):
            if not company.with_context(date=datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)).vat_payer:
                continue
            if company.auto_lock_day_non_advisers > 0:
                non_accountant_lock_date += relativedelta(months=1, day=company.auto_lock_day_non_advisers)
            if company.auto_lock_day_advisers > 0:
                accountant_lock_date += relativedelta(months=1, day=company.auto_lock_day_advisers)
            company.period_lock_date = non_accountant_lock_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            company.accountant_lock_date = accountant_lock_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
