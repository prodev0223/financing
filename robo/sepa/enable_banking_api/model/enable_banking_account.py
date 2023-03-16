# -*- coding: utf-8 -*-
from odoo import models, api, fields, exceptions, _


class EnableBankingAccount(models.Model):
    _name = 'enable.banking.account'
    _description = 'Model that stores enable banking account data'

    # Identifier fields
    external_id = fields.Char(string='External ID', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
    )
    bank_connector_id = fields.Many2one(
        'enable.banking.connector',
        string='Connector', required=True
    )
    account_iban = fields.Char(
        string='Bank account (IBAN)', required=True,
    )
    # Balance amounts
    api_end_balance = fields.Float(string='API end balance')
    api_balance_update_date = fields.Datetime(
        string='API balance update date',
        inverse='_set_api_balance_update_date'
    )
    journal_id = fields.Many2one('account.journal', string='Related journal')
    active = fields.Boolean(string='Active', default=True)
    configured_connector = fields.Boolean(compute='_compute_configured_connector')

    # Inverses / Computes ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_configured_connector(self):
        """Checks whether related connector is configured"""
        for rec in self:
            rec.configured_connector = rec.bank_connector_id and rec.bank_connector_id.api_state == 'working'

    @api.multi
    def _set_api_balance_update_date(self):
        """Updates related journal values on API balance update date changes"""
        for rec in self:
            rec.journal_id.write({
                'api_end_balance': rec.api_end_balance,
                'api_balance_update_date': rec.api_balance_update_date,
            })
            rec.journal_id._compute_api_integrated_bank()

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    def _check_external_id(self):
        """Ensure that external ID is unique per connector"""
        for rec in self:
            if self.with_context(active_test=False).search_count([
                ('external_id', '=', rec.external_id),
                ('bank_connector_id', '=', rec.bank_connector_id.id),
            ]) > 1:
                raise exceptions.ValidationError(
                    _('Enable banking account with external ID {} already exists!').format(rec.external_id)
                )

    @api.multi
    def _check_journal_id(self):
        """Ensure that journal ID is unique"""
        for rec in self.filtered('journal_id'):
            if self.with_context(active_test=False).search_count([('journal_id', '=', rec.journal_id.id)]) > 1:
                raise exceptions.ValidationError(
                    _('Enable banking account with journal {} already exists!').format(rec.journal_id.name)
                )

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def relate_account_journals(self):
        """
        Method that either creates or relates already
        existing account journal records to
        passed enable banking account records
        """
        company_currency = self.env.user.company_id.currency_id
        journal_ob = self.sudo().env['account.journal']
        # Loop trough records and activate them
        for rec in self.filtered(lambda x: x.active):
            res_bank = rec.bank_connector_id.bank_id
            journal = rec.journal_id
            # If journal does not exist, try to search for it
            if not journal:
                # Build a domain, if company currency differs
                # from IBAN currency, add it to search domain
                domain = [('bank_acc_number', '=', rec.account_iban), ('type', '=', 'bank')]
                if rec.currency_id.id != company_currency.id:
                    domain += [('currency_id', '=', rec.currency_id.id)]
                else:
                    domain += ['|', ('currency_id', '=', company_currency.id), ('currency_id', '=', False)]
                journal = journal_ob.search(domain, limit=1)
                # If journal does not exist, create it
                if not journal:
                    code = journal_ob.get_journal_code_bank()
                    journal_vals = {
                        'name': '%s (%s) %s' % (res_bank.name, rec.account_iban[-4:], rec.currency_id.name),
                        'code': code,
                        'type': 'bank',
                        'company_id': self.env.user.company_id.id,
                        'bank_acc_number': rec.account_iban,
                        'bank_id': res_bank.id,
                    }
                    if rec.currency_id.id != company_currency.id:
                        journal_vals.update({'currency_id': rec.currency_id.id})
                    journal = journal_ob.create(journal_vals)
                # Write newly created, or found journal to the record
                rec.write({'journal_id': journal.id})

    @api.multi
    def fetch_account_balance(self):
        """
        Fetches balance for current batch of passed enable banking
        accounts. Can either be called from a button inside the
        account or from a controller for all of the related accounts
        """
        self.env['enable.banking.api.base'].api_get_accounts_balances(
            e_banking_accounts=self,
        )

    # Buttons ---------------------------------------------------------------------------------------------------------

    @api.multi
    def button_fetch_account_balance(self):
        """Button to fetch the balance for current account"""
        self.ensure_one()
        if self.bank_connector_id.api_state != 'working':
            raise exceptions.ValidationError(
                _('You cannot execute this action, connector session is not active')
            )
        self.fetch_account_balance()

    @api.multi
    def button_toggle_active(self):
        """Button to either enable or disable banking account"""
        for rec in self:
            rec.active = not rec.active
