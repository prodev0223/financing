# -*- encoding: utf-8 -*-
from odoo import fields, models, api


class AutomaticReconciliationSettings(models.TransientModel):
    _name = 'automatic.reconciliation.settings'

    @api.model
    def default_get(self, field_list):
        """
        Default get override - get automatic reconciliation settings from res.company
        :param field_list: current models' field list
        :return: default values (dict)
        """
        res = super(AutomaticReconciliationSettings, self).default_get(field_list)
        company = self.sudo().env.user.company_id

        # Gather up the items from res company
        partner_items = [
            (0, 0, {'partner_id': partner.id})
            for partner in company.auto_reconciliation_excluded_partner_ids
        ]
        excluded_account_items = [
            (0, 0, {'exc_account_id': account.id, })
            for account in company.auto_reconciliation_excluded_account_ids
        ]
        included_account_items = [
            (0, 0, {'inc_account_id': account.id, })
            for account in company.auto_reconciliation_included_account_ids
        ]
        journal_items = [
            (0, 0, {'journal_id': journal.id, })
            for journal in company.auto_reconciliation_excluded_journal_ids
        ]

        # Update result with default values and return it
        res.update({
            'partner_item_ids': partner_items,
            'excluded_account_item_ids': excluded_account_items,
            'included_account_item_ids': included_account_items,
            'journal_item_ids': journal_items,
            'disable_automatic_reconciliation': company.disable_automatic_reconciliation,
            'disable_automatic_structured_reconciliation': company.disable_automatic_structured_reconciliation,
            'automatic_reconciliation_sorting': company.automatic_reconciliation_sorting or 'date_asc',
            'automatic_bank_reconciliation': company.automatic_bank_reconciliation,
            'automatic_reconciliation_filtering': company.automatic_reconciliation_filtering,
        })
        return res

    # Base automatic reconciliation settings
    disable_automatic_reconciliation = fields.Boolean(string='Išjungti automatinį dengimą')
    disable_automatic_structured_reconciliation = fields.Boolean(string='Išjungti struktūruotų banko įšrašų dengimą')
    automatic_reconciliation_sorting = fields.Selection(
        [('date_asc', 'Nuo seniausios datos'),
         ('date_desc', 'Nuo naujausios datos')],
        string='Automatinio dengimo grupavimas'
    )
    automatic_bank_reconciliation = fields.Selection([
        ('full_reconcile', 'Drausti dalinį sudengimą'),
        ('partial_reconcile', 'Įgalinti dalinį sudengimą visoms sumoms'),
        ('partial_reconcile_receivable', 'Įgalinti dalinį sudengimą gautinoms sumoms'),
        ('partial_reconcile_payable', 'Įgalinti dalinį sudengimą mokėtinoms sumoms'),
    ],
        string='Dalinio sudengimo nustatymai', default='full_reconcile',
        help='Įjungus dalinio sudengimo draudimą importuojami banko išrašai automatiškai bus dengiami tik tada, '
             'jei apskaitoje randamas įrašas(-ai) su identiška suma.',
    )

    automatic_reconciliation_filtering = fields.Selection([
        ('payment_name', 'Search for reconciliation entries using payment name only'),
        ('payment_amount', 'Search for reconciliation entries using payment amount only'),
        ('payment_name_and_amount', 'Search for reconciliation entries using name and amount'),
    ], string='Reconciliation entry filtering settings')

    # Fields that are used to select partners/accounts/journals
    partner_item_ids = fields.One2many('automatic.reconciliation.settings.item', 'settings_id')
    excluded_account_item_ids = fields.One2many('automatic.reconciliation.settings.item', 'settings_id')
    included_account_item_ids = fields.One2many('automatic.reconciliation.settings.item', 'settings_id')
    journal_item_ids = fields.One2many('automatic.reconciliation.settings.item', 'settings_id')

    # Computed fields used to filter out already selected partners/accounts/journals from the drop-down
    partner_ids = fields.Many2many('res.partner', compute='_compute_partner_ids')
    excluded_account_ids = fields.Many2many('account.account', compute='_compute_excluded_account_ids')
    included_account_ids = fields.Many2many('account.account', compute='_compute_included_account_ids')
    journal_ids = fields.Many2many('account.journal', compute='_compute_journal_ids')

    @api.multi
    @api.depends('partner_item_ids.partner_id')
    def _compute_partner_ids(self):
        """
        Compute already selected partner_ids for domain to filter them
        :return: None
        """
        for rec in self:
            rec.partner_ids = rec.mapped('partner_item_ids.partner_id.id')

    @api.multi
    @api.depends('excluded_account_item_ids.exc_account_id')
    def _compute_excluded_account_ids(self):
        """
        Compute already selected excluded
        account_ids for domain to filter them
        :return: None
        """
        for rec in self:
            rec.excluded_account_ids = rec.mapped('excluded_account_item_ids.exc_account_id.id')

    @api.multi
    @api.depends('included_account_item_ids.inc_account_id')
    def _compute_included_account_ids(self):
        """
        Compute already selected included
        account_ids for domain to filter them
        :return: None
        """
        for rec in self:
            rec.included_account_ids = rec.mapped('included_account_item_ids.inc_account_id.id')

    @api.multi
    @api.depends('journal_item_ids.journal_id')
    def _compute_journal_ids(self):
        """
        Compute already selected journal_ids for domain to filter them
        :return: None
        """
        for rec in self:
            rec.journal_ids = rec.mapped('journal_item_ids.journal_id.id')

    @api.multi
    def set_reconciliation_info(self):
        """
        Write automatic reconciliation info to company settings
        :return: None
        """
        self.ensure_one()
        values = {
            'auto_reconciliation_excluded_partner_ids': [
                (6, 0, self.partner_item_ids.mapped('partner_id.id'))
            ],
            'auto_reconciliation_excluded_account_ids': [
                (6, 0, self.excluded_account_item_ids.mapped('exc_account_id.id'))
            ],
            'auto_reconciliation_included_account_ids': [
                (6, 0, self.included_account_item_ids.mapped('inc_account_id.id'))
            ],
            'auto_reconciliation_excluded_journal_ids': [
                (6, 0, self.journal_item_ids.mapped('journal_id.id'))
            ],
            'disable_automatic_structured_reconciliation': self.disable_automatic_structured_reconciliation,
            'disable_automatic_reconciliation': self.disable_automatic_reconciliation,
            'automatic_reconciliation_sorting': self.automatic_reconciliation_sorting,
            'automatic_bank_reconciliation': self.automatic_bank_reconciliation,
            'automatic_reconciliation_filtering': self.automatic_reconciliation_filtering,
        }
        self.sudo().env.user.company_id.write(values)
