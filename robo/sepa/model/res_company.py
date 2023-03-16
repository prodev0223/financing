# -*- encoding: utf-8 -*-
from odoo import fields, models, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    bank_commission_account_id = fields.Many2one('account.account', string='Banko komisinių nurašymo sąskaita')
    auto_reconciliation_excluded_partner_ids = fields.Many2many(
        'res.partner', string='Partneriai praleidžiami automatinio banko dengimo metu')
    auto_reconciliation_excluded_account_ids = fields.Many2many(
        'account.account', string='Sąskaitos praleidžiamos automatinio banko dengimo metu')
    # Define separate relation, so both account m2m fields are not mixed up
    auto_reconciliation_included_account_ids = fields.Many2many(
        'account.account', string='Sąskaitos traukiamos automatinio banko dengimo metu',
        relation='account_account_res_company_reconciliation_included_relation',
    )
    auto_reconciliation_excluded_journal_ids = fields.Many2many(
        'account.journal', string='Žurnalai praleidžiami automatinio banko dengimo metu')
    disable_automatic_reconciliation = fields.Boolean(string='Išjungti automatinį dengimą')
    disable_automatic_structured_reconciliation = fields.Boolean(string='Išjungti automatinį dengimą')
    automatic_reconciliation_sorting = fields.Selection([('date_asc', 'Nuo seniausios datos'),
                                                         ('date_desc', 'Nuo naujausios datos')],
                                                        string='Automatinio dengimo grupavimas')
    automatic_bank_reconciliation = fields.Selection([
        ('full_reconcile', 'Drausti dalinį sudengimą'),
        ('partial_reconcile', 'Įgalinti dalinį sudengimą visoms sumoms'),
        ('partial_reconcile_receivable', 'Įgalinti dalinį sudengimą gautinoms sumoms'),
        ('partial_reconcile_payable', 'Įgalinti dalinį sudengimą mokėtinoms sumoms'),
    ],
        string='Dalinio sudengimo nustatymai',
        default='full_reconcile',
    )

    automatic_reconciliation_filtering = fields.Selection([
        ('payment_name', 'Search for reconciliation entries using payment name only'),
        ('payment_amount', 'Search for reconciliation entries using payment amount only'),
        ('payment_name_and_amount', 'Search for reconciliation entries using name and amount'),
    ],
        string='Reconciliation entry filtering settings',
        compute='_compute_automatic_reconciliation_filtering',
        inverse='_set_automatic_reconciliation_filtering',
    )

    @api.multi
    def _compute_automatic_reconciliation_filtering(self):
        """Get automatic reconciliation settings from the parameters"""
        self.ensure_one()
        filtering_settings = self.env['ir.config_parameter'].sudo().get_param(
            'automatic_reconciliation_filtering', 'payment_name_and_amount')
        self.automatic_reconciliation_filtering = filtering_settings

    @api.multi
    def _set_automatic_reconciliation_filtering(self):
        """Set automatic reconciliation settings"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'automatic_reconciliation_filtering',
            str(self.automatic_reconciliation_filtering),
        )

    @api.multi
    def get_employee_advance_account(self):
        """Method meant to be overridden"""
        self.ensure_one()
        return self.env['account.account']
