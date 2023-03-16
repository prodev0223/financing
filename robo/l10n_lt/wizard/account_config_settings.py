# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    income_currency_exchange_account_id = fields.Many2one('account.account', string='Gain Exchange Rate Account',
                                                          domain=[('internal_type', '=', 'other'),
                                                                  ('deprecated', '=', False)],
                                                          related='company_id.income_currency_exchange_account_id')
    expense_currency_exchange_account_id = fields.Many2one('account.account', string='Loss Exchange Rate Account',
                                                           domain=[('internal_type', '=', 'other'),
                                                                   ('deprecated', '=', False)],
                                                           related='company_id.expense_currency_exchange_account_id')
    default_property_account_receivable_id = fields.Many2one('account.account',
                                                             string='Default partner account receivable',
                                                             # related='company_id.default_property_account_receivable_id',
                                                             domain="[('internal_type', '=', 'receivable'), ('deprecated', '=', False)]")
    default_property_account_payable_id = fields.Many2one('account.account',
                                                          string='Default partner account payable',
                                                          # related='company_id.default_property_account_payable_id',
                                                          domain="[('internal_type', '=', 'payable'), ('deprecated', '=', False)]")
    vat_account_ids = fields.Many2many('account.account', 'company_account_vat_rel', string='Pvm sąskaitos',
                                       help='Sąskaitos PVM sudengimui', related='company_id.vat_account_ids')
    import_vat_account_ids = fields.Many2many('account.account', 'company_account_vat_import_rel',
                                              string='Importo PVM sąskaitos',
                                              help='Sąskaitos importo PVM sudengimui',
                                              related='company_id.import_vat_account_ids')
    vat_account_id = fields.Many2one('account.account', string='Mokėtino PVM sąskaita',
                                     related='company_id.vat_account_id')
    import_vat_account_id = fields.Many2one('account.account', string='Mokėtino importo PVM sąskaita',
                                            related='company_id.import_vat_account_id')
    vat_journal_id = fields.Many2one('account.journal', string='PVM žurnalas', related='company_id.vat_journal_id')
    auto_lock_day_non_advisers = fields.Integer(string='DK įrašų užrakinimo diena ne buhalteriams',
                                                related='company_id.auto_lock_day_non_advisers')
    auto_lock_day_advisers = fields.Integer(string='DK įrašų užrakinimo diena buhalteriams',
                                            related='company_id.auto_lock_day_advisers')
    auto_lock_day = fields.Integer(string='DK įrašų užrakinimo diena', related='company_id.auto_lock_day')
    bank_commission_account_id = fields.Many2one('account.account', string='Banko komisinių nurašymo sąskaita',
                                                 related='company_id.bank_commission_account_id')
    cashier_id = fields.Many2one('hr.employee', string='Kasininkas',
                                 help='Kasos orderiuose nurodomas kasininkas',
                                 related='company_id.cashier_id')
    cashier_manager_id = fields.Many2one('hr.employee', string='Kasininko vadovas',
                                         help='Kasos orderius patvirtinantis asmuo',
                                         related='company_id.cashier_manager_id')
    cashier_accountant_id = fields.Many2one('res.partner', string='Vyr. buhalteris (buhalteris)',
                                            help='Kasos orderius patvirtinantis asmuo',
                                            related='company_id.cashier_accountant_id')
    period_close_journal_id = fields.Many2one('account.journal', string='Periodo uždarymo žurnalas',
                                              related='company_id.period_close_journal_id')
    cash_receipt_journal_id = fields.Many2one('account.journal', string='Pinigų kvitų žurnalas',
                                              related='company_id.cash_receipt_journal_id')
    accountant_lock_date = fields.Date(string="Lock Date for Accountants", related='company_id.accountant_lock_date',
                                       help="Only chief accountants will be able to edit accounts prior to and inclusive of this date.")

    @api.multi
    def set_default_property_account_ids(self):
        ir_values_obj = self.env['ir.values']
        if self.default_property_account_receivable_id:
            ir_values_obj.sudo().set_default('res.partner', "property_account_receivable_id",
                                             self.default_property_account_receivable_id.id,
                                             for_all_users=True, company_id=self.company_id.id)
        if self.default_property_account_payable_id:
            ir_values_obj.sudo().set_default('res.partner', "property_account_payable_id",
                                             self.default_property_account_payable_id.id,
                                             for_all_users=True, company_id=self.company_id.id)

    @api.model
    def get_default_partner_accounts(self, fields):
        default_property_account_receivable_id = False
        default_property_account_payable_id = False
        if 'default_property_account_payable_id' in fields:
            default_property_account_receivable_id = self.env['ir.values'].get_default('res.partner',
                                                                                       'property_account_payable_id',
                                                                                       company_id=self.env.user.company_id.id)
        if 'default_property_account_receivable_id' in fields:
            default_property_account_payable_id = self.env['ir.values'].get_default('res.partner',
                                                                                    'property_account_receivable_id',
                                                                                    company_id=self.env.user.company_id.id)
        return {
            'default_property_account_receivable_id': default_property_account_receivable_id,
            'default_property_account_payable_id': default_property_account_payable_id,
        }

    @api.multi
    def set_chart_of_accounts(self):
        ret = super(AccountConfigSettings, self.with_context(show_views=True)).set_chart_of_accounts()
        self.env['account.account'].recalculate_hierarchy()
        return ret
