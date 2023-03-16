# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from datetime import datetime, timedelta
import braintree


class BraintreeMerchantAccount(models.Model):
    _name = 'braintree.merchant.account'

    # Identification fields
    name = fields.Char(required=True, translate=False, inverse='_set_name')
    gateway_id = fields.Many2one('braintree.gateway', required=True, string='Related gateway')
    # Related transactions
    transaction_ids = fields.One2many('braintree.transaction', 'merchant_account_id')
    # Related base objects
    journal_id = fields.Many2one('account.journal', string='Journal')
    currency_id = fields.Many2one('res.currency', string='Currency')
    status = fields.Selection(
        [('pending', 'Pending'),
         ('active', 'Active'),
         ('suspended', 'Suspended')], name='Status',
    )
    # Misc fields
    last_fetch_date = fields.Datetime(string='Last automated transaction fetch')
    use_custom_allowed_difference = fields.Boolean(string='Custom allowed reconciliation difference')
    allowed_reconciliation_difference = fields.Float(
        string='Allowed reconciliation difference',
        help='Maximum price mismatch allowed for automatic reconciliation',
    )

    # Inverses --------------------------------------------------------------------------------------------------------

    @api.multi
    def _set_name(self):
        """ Create related journal and account records when the name is set """
        company_currency = self.env.user.company_id.sudo().currency_id
        for rec in self.filtered(lambda x: not x.journal_id):
            non_company_currency = rec.currency_id and rec.currency_id != company_currency
            account_prefix = rec.gateway_id.account_prefix

            # Build journal code from account name
            journal_code = 'BT{}'.format(rec.name[:3].upper())
            journal_domain = [
                ('import_file_type', '=', 'braintree_api'),
                ('code', '=', journal_code),
                ('currency_id', '=', rec.currency_id.id if non_company_currency else False),
            ]
            # Search for the journal, and create it if it does not exist
            account_journal = self.env['account.journal'].search(journal_domain)
            if not account_journal:
                currency_id = rec.currency_id.id if non_company_currency else False
                m_name = 'Braintree (%s) (%s) %s' % (journal_code, rec.gateway_id.name, rec.currency_id.name)

                # Search for unused account code
                account_code = self.env['ir.sequence'].next_by_code('braintree.api.account')
                while self.env['account.account'].search([('code', '=', account_prefix + str(account_code))]):
                    account_code = self.env['ir.sequence'].next_by_code('braintree.api.account')

                # Create an account
                account = self.env['account.account'].create({
                    'code': account_prefix + str(account_code),
                    'currency_id': currency_id,
                    'company_id': self.env.user.company_id.id,
                    'name': m_name,
                    'user_type_id': self.env.ref('account.data_account_type_liquidity').id,
                })
                # Create the journal
                account_journal = self.env['account.journal'].create({
                    'name': m_name,
                    'code': journal_code,
                    'currency_id': currency_id,
                    'type': 'bank',
                    'import_file_type': 'braintree_api',
                    'default_debit_account_id': account.id,
                    'default_credit_account_id': account.id,
                    'update_posted': True,
                })
            rec.journal_id = account_journal
            # Manually recompute API integrated bank fields
            account_journal._compute_api_integrated_bank()

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('journal_id', 'currency_id')
    def _check_currency_id(self):
        """ Ensures that journal currency and merchant currency are the same """
        company_currency = self.env.user.company_id.sudo().currency_id
        for rec in self.filtered('journal_id'):
            journal_currency = rec.journal_id.currency_id or company_currency
            currency = rec.currency_id or company_currency
            if currency != journal_currency:
                raise exceptions.ValidationError(
                    _('The merchant account currency (%s) does not match the journal currency (%s)') %
                    (currency.name, journal_currency.name)
                )

    @api.multi
    @api.constrains('journal_id')
    def _check_journal_id(self):
        """ Ensures that journal is unique per merchant accounts """
        for rec in self.filtered('journal_id'):
            if self.search_count([('journal_id', '=', rec.journal_id.id)]) > 1:
                raise exceptions.ValidationError(_('You cannot have two merchant accounts with the same journal'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.model
    def api_fetch_transactions(self, journal=None, date_from=None, date_to=None):
        """
        API Method //
        Used to fetch all new transactions since the last fetch (uses last_fetch_date field to find this)
        or based on passed dates. Method can also be used on a specific journal or on all of the merchant accounts.
        Method argument structure is maintained so it matches api_bank_integration structure.
        """
        def convert_dates(date_str):
            """Convert date string to datetime object"""
            try:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except ValueError:
                date_dt = datetime.strptime(date_str, tools.DEFAULT_SERVER_DATE_FORMAT)
            return date_dt

        # Convert dates to datetime objects
        date_from_dt = convert_dates(date_from) if date_from else None
        date_to_dt = convert_dates(date_to) if date_from else datetime.utcnow()
        merchant_accounts = self.get_configured_accounts(journal)

        gateways = merchant_accounts.mapped('gateway_id')
        gateway_map = {g.id: g.api_init_gateway() for g in gateways if g.check_api()}
        # Loop through accounts and fetch the transactions
        for merchant_account in merchant_accounts:
            gateway = merchant_account.gateway_id
            # Get current gateway based on the account, if it's not in the mapper
            # i.e. not configured - skip current account transaction fetch
            gateway_endpoint = gateway_map.get(gateway.id)
            if not gateway_endpoint or merchant_account.status != 'active':
                continue
            # Get gateway init date, and last fetch date if no dates are passed
            if not date_from_dt:
                gateway_date_start = datetime.strptime(
                    gateway.gateway_init_date, tools.DEFAULT_SERVER_DATETIME_FORMAT
                )
                last_fetch = gateway_date_start
                if merchant_account.last_fetch_date:
                    last_fetch = datetime.strptime(
                        merchant_account.last_fetch_date, tools.DEFAULT_SERVER_DATETIME_FORMAT
                    )
                # Give 15 minutes of margin before the last fetch
                date_from_dt = last_fetch - timedelta(minutes=15)
                date_from_dt = max(date_from_dt, gateway_date_start)
            # Call the gateway endpoint to get the transactions
            fetched_transactions = gateway_endpoint.transaction.search(
                braintree.TransactionSearch.created_at.between(date_from_dt, date_to_dt),
                (braintree.TransactionSearch.type == braintree.Transaction.Type.Sale),
                (braintree.TransactionSearch.merchant_account_id == merchant_account.name),
                (braintree.TransactionSearch.payment_instrument_type == 'credit_card'),
            )
            new_transactions = self.env['braintree.transaction']
            # Loop through fetched items and create new Braintree transactions
            for transaction in fetched_transactions.items:
                braintree_transaction = new_transactions.create_from_braintree(transaction, gateway)
                if braintree_transaction:
                    new_transactions |= braintree_transaction
            merchant_account.last_fetch_date = date_to_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            new_transactions.create_bank_statement()

    @api.multi
    def update_merchant_account(self, merchant_account):
        """Updates current record status and currency ID"""
        self.ensure_one()
        # Prepare the dict of new values
        new_values = {}
        currency = self.currency_id.name if self.currency_id else self.env.user.company_id.currency_id.name
        # Check transaction status changes
        if self.status != merchant_account.status:
            new_values['status'] = merchant_account.status
        # Check for any currency changes
        if merchant_account.currency_iso_code != currency:
            updated_currency = self.env['res.currency'].search([('name', '=', merchant_account.currency_iso_code)])
            if updated_currency:
                new_values['currency_id'] = updated_currency.id
        # Write new values if any
        if new_values:
            self.write(new_values)

    @api.model
    def get_configured_accounts(self, journal=None):
        """Returns recordset of configured merchant accounts"""
        base_domain = [
            ('status', '=', 'active'), ('gateway_id.api_state', '=', 'working'),
            ('gateway_id.initially_authenticated', '=', True),
        ]
        # Append journal filtering if flag is set
        if journal:
            base_domain += [('journal_id', '=', journal.id)]
        # Search for merchant accounts
        merchant_accounts = self.env['braintree.merchant.account'].search(base_domain)
        return merchant_accounts

    # Actions / Buttons -----------------------------------------------------------------------------------------------

    @api.multi
    def button_fetch_transactions(self):
        """ Button to fetch transactions on the selected merchant account"""
        self.ensure_one()
        if not self.gateway_id.initially_authenticated or self.gateway_id.api_state != 'working':
            raise exceptions.ValidationError(
                _('You cannot fetch transactions for an account that belongs to non-configured gateway.')
            )
        self.api_fetch_transactions(journal=self.journal_id)

    @api.multi
    def action_open_transactions(self):
        """
        Opens a view to all transactions from that gateway
        :return: action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.braintree_transaction_action')
        action = action.read()[0]
        action['domain'] = [('merchant_account_id', '=', self.id)]
        action['view_mode'] = 'tree'
        return action

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """ Checks that no transaction is linked to the merchant account before allowing to delete """
        if any(rec.transaction_ids for rec in self):
            raise exceptions.UserError(
                _('You cannot delete this merchant account because there are linked transactions.')
            )
        return super(BraintreeMerchantAccount, self).unlink()

    # Cron Jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_braintree_transaction_fetch(self):
        """ Fetch transactions on all existing merchant account """
        self.env['braintree.merchant.account'].api_fetch_transactions()
