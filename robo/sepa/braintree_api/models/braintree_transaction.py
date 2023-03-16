# -*- coding: utf-8 -*-
from odoo import api, exceptions, fields, models, tools, _
import logging

_logger = logging.getLogger(__name__)
UPDATABLE_STATES = ['authorized', 'authorizing', 'settlement_pending', 'settling', 'submitted_for_settlement']
DECLINED_STATES = ['gateway_rejected', 'processor_declined']


class BraintreeTransaction(models.Model):
    _name = 'braintree.transaction'
    _order = 'created_at desc, create_date desc'

    # Identification fields
    global_id = fields.Char(required=True, readonly=True)
    transaction_id = fields.Char(string='External ID', readonly=True, help='Braintree internal transaction ID')
    order_id = fields.Char(string='Order ID', help='Order ID as transmitted through the payment processing')
    # Related gateway and account
    gateway_id = fields.Many2one('braintree.gateway', required=True, readonly=True)
    merchant_account_id = fields.Many2one(
        'braintree.merchant.account', string='Merchant account',
        required=True, readonly=True,
    )
    # Related base objects
    bank_statement_line_id = fields.Many2one(
        'account.bank.statement.line', string='Bank statement line',
    )
    journal_id = fields.Many2one(related='merchant_account_id.journal_id', string='Journal')
    currency_id = fields.Many2one('res.currency', string='Currency')

    date = fields.Date(compute='_compute_date', store=True, string='Date')
    created_at = fields.Datetime(string='Transaction creation date')
    amount = fields.Monetary(string='Transaction amount')

    # Disbursement fields
    disbursement_date = fields.Date(string='Disbursement date')
    is_disbursed = fields.Boolean(string='Disbursed transaction')
    disbursement_amount = fields.Monetary(string='Disbursement transaction amount')
    disbursement_bank_statement_line_id = fields.Many2one(
        'account.bank.statement.line', string='Disbursement bank statement line',
    )

    # States / types
    payment_instrument_type = fields.Selection([
        ('android_pay_card', 'Android Pay'),
        ('apple_pay_card', 'Apple Pay'),
        ('credit_card', 'Credit card'),
        ('masterpass_card', 'Masterpass card'),
        ('paypal_account', 'Paypal account'),
        ('paypal_here', 'Paypal Here'),
        ('samsung_pay_card', 'Samsung Pay'),
        ('us_bank_account', 'US bank account'),
        ('venmo_account', 'Venmo'),
        ('visa_checkout_card', 'Visa checkout card'),
    ], string='Method of payment'
    )
    status = fields.Selection([
        ('authorization_expired', 'Authorization expired'),
        ('authorized', 'Authorized'),
        ('authorizing', 'Authorizing'),
        ('settlement_pending', 'Settlement pending'),
        ('settlement_declined', 'Settlement declined'),
        ('failed', 'Failed'),
        ('gateway_rejected', 'Gateway rejected'),
        ('processor_declined', 'Processor declined'),
        ('settled', 'Settled'),
        ('settling', 'Settling'),
        ('submitted_for_settlement', 'Submitted for settlement'),
        ('voided', 'Voided')], string='Status (Braintree)'
    )
    escrow_status = fields.Selection([
        ('hold_pending', 'hold_pending'),
        ('held', 'held'),
        ('release_pending', 'release_pending'),
        ('released', 'released'),
        ('refunded', 'refunded')], string='Escrow status'
    )
    # Partner fields
    customer_id = fields.Many2one('braintree.customer', string='Braintree customer')
    partner_id = fields.Many2one('res.partner', string='Partner', inverse='_set_partner_id')

    # Misc fields
    allowed_reconciliation_difference = fields.Float(
        string='Allowed reconciliation difference', compute='_compute_allowed_reconciliation_difference',
        help='Maximum price mismatch allowed for automatic reconciliation'
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('created_at')
    def _compute_date(self):
        """Calculate transaction date based on creation date"""
        for rec in self:
            rec.date = rec.created_at.split()[0] if rec.created_at else False

    @api.multi
    @api.depends(
        'merchant_account_id.use_custom_allowed_difference',
        'merchant_account_id.allowed_reconciliation_difference',
        'gateway_id.allowed_reconciliation_difference',
    )
    def _compute_allowed_reconciliation_difference(self):
        """Calculate allowed reconciliation difference by either taking the value from gateway or account"""
        for rec in self:
            reconciliation_difference = rec.gateway_id.allowed_reconciliation_difference
            if rec.merchant_account_id.use_custom_allowed_difference:
                reconciliation_difference = rec.merchant_account_id.allowed_reconciliation_difference
            rec.allowed_reconciliation_difference = reconciliation_difference

    @api.multi
    def _set_partner_id(self):
        """ Update bank statement line partner_id on write """
        for tr in self:
            if not tr.bank_statement_line_id or tr.journal_entry_ids:
                continue
            tr.bank_statement_line_id.write({'partner_id': tr.partner_id.id})

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('journal_id', 'currency_id')
    def _check_currency_id(self):
        """Ensure that transaction currency matches journal currency"""
        c_currency = self.env.user.company_id.sudo().currency_id
        for rec in self:
            # Either assigned or company currency
            journal_currency = rec.journal_id.currency_id or c_currency
            currency = rec.currency_id or c_currency
            if currency != journal_currency:
                raise exceptions.ValidationError(
                    _('The transaction currency (%s) does not match the journal currency (%s)') %
                    (currency.name, journal_currency.name)
                )

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """Deny unlinking of the transaction if there's any related statement lines"""
        if any(rec.bank_statement_line_id for rec in self):
            raise exceptions.UserError(
                _('You cannot delete this transaction because there is a linked bank statement line.')
            )
        return super(BraintreeTransaction, self).unlink()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def api_update_transactions(self, disbursement_mode=False):
        """
        API Method //
        Update transactions by remotely checking their changes
        :param disbursement_mode: Indicates whether disbursement changes should be checked
        :return: None
        """
        gateways = self.mapped('gateway_id')
        gateway_map = {g.id: g.api_init_gateway() for g in gateways}
        updated_transactions = self.env['braintree.transaction']
        for system_transaction in self:
            # Check for corresponding gateways
            gateway = gateway_map.get(system_transaction.gateway_id.id)
            if not gateway:
                continue
            # Get the transaction and check the differences between system transaction
            tr_id = system_transaction.transaction_id
            try:
                ext_transaction = gateway.transaction.find(tr_id)
            except Exception as exc:
                _logger.info('Braintree transaction [{}] update exception: {}'.format(tr_id, str(exc.args)))
                continue

            tr_values = {}
            if disbursement_mode and ext_transaction.disbursement_details.success:
                tr_values.update({
                    'disbursement_date': ext_transaction.disbursement_details.disbursement_date,
                    'disbursement_amount': ext_transaction.disbursement_details.settlement_amount,
                    'is_disbursed': True,
                })
            elif not disbursement_mode:
                if system_transaction.status != ext_transaction.status:
                    tr_values['status'] = ext_transaction.status
                if not system_transaction.order_id:
                    tr_values['order_id'] = ext_transaction.order_id
                if not system_transaction.partner_id:
                    customer_details = ext_transaction.customer_details
                    customer = self.env['braintree.customer'].get_from_customer_details(
                        customer_details, extra_data={'gateway_id': system_transaction.gateway_id.id}
                    )
                    # If related customer was found, update customer and partner IDs
                    if customer:
                        tr_values.update({
                            'customer_id': customer.id,
                            'partner_id': customer.partner_id.id,
                        })
            # Write the values and append transaction to updated list
            if tr_values:
                system_transaction.write(tr_values)
                updated_transactions |= system_transaction

        if updated_transactions:
            updated_transactions.create_bank_statement()

    @api.model
    def create_from_braintree(self, transaction, gateway):
        """
        Create a record from the data provided by the BrainTree API
        :param transaction: Transaction data provided by API (dict)
        :param gateway: Transaction gateway (record)
        :return: braintree.transaction (record)
        """
        # Skip the creation if same global ID already exists
        if self.env['braintree.transaction'].search_count([('global_id', '=', transaction.global_id)]):
            return
        # Raise if non existing currency was passed
        currency = self.env['res.currency'].search([('name', '=', transaction.currency_iso_code)])
        if not currency:
            raise exceptions.UserError('Currency not found')
        # Search for related merchant account
        merchant_account = self.env['braintree.merchant.account'].search(
            [('name', '=', transaction.merchant_account_id)], limit=1)
        # Fetch related customer details
        customer_details = transaction.customer_details
        customer = self.env['braintree.customer'].get_from_customer_details(
            customer_details, extra_data={'gateway_id': gateway.id}
        )
        # Determine partner to use, forced gateway partner takes priority
        partner_to_use = gateway.forced_partner_id or customer.partner_id
        # Prepare the values and create the transaction
        vals = {
            'gateway_id': gateway.id,
            'merchant_account_id': merchant_account.id,
            'currency_id': currency.id,
            'status': transaction.status,
            'transaction_id': transaction.id,
            'order_id': transaction.order_id,
            'payment_instrument_type': transaction.payment_instrument_type,
            'amount': transaction.amount,
            'customer_id': customer.id,
            'global_id': transaction.global_id,
            'created_at': transaction.created_at,
            'partner_id': partner_to_use.id,
            'imported_partner_name': partner_to_use.name,
            'imported_partner_code': partner_to_use.kodas,
        }
        # Append disbursement data if it exists
        if transaction.disbursement_details.success:
            # Get the disbursement sign, opposite of the original amount sign
            disbursement_sign = -1 if tools.float_compare(
                float(transaction.amount), 0.0, precision_digits=2) > 0 else 1
            vals.update({
                'disbursement_date': transaction.disbursement_details.disbursement_date,
                'disbursement_amount': float(
                    transaction.disbursement_details.settlement_amount) * disbursement_sign,
                'is_disbursed': True,
            })
        return self.env['braintree.transaction'].create(vals)

    @api.multi
    def add_line_to_statement(self, statement, disbursement_mode=False):
        """
        Adds a new line to statement
        :param statement: account.bank.statement record to which we add the transactions
        :param disbursement_mode: Indicates whether statement/line is being
        created for original transaction or disbursement transaction
        :return: Created 'account.bank.statement.line' (records)
        """
        # Create the lines based on passed recordset
        lines = self.env['account.bank.statement.line']
        for transaction in self:
            # Build reference numbers based on disbursement mode
            extra_ref = '--DISBURSEMENT' if disbursement_mode else str()
            ref_number = 'Braintree {}{}'.format(transaction.transaction_id, extra_ref)
            entry_reference = '{}{}'.format(transaction.global_id, extra_ref)

            vals = {
                'statement_id': statement.id,
                'ref': ref_number,
                'name': transaction.order_id or _('Unknown order ID'),
                'entry_reference': entry_reference,
                'info_type': 'unstructured',
                'partner_id': transaction.partner_id.id,
            }
            # Line values differ based on the disbursement_mode flag
            if disbursement_mode:
                vals.update({
                    'braintree_disbursement_transaction_ids': [(4, transaction.id)],
                    'date': transaction.disbursement_date,
                    'amount': transaction.disbursement_amount,
                })
            else:
                vals.update({
                    'braintree_transaction_ids': [(4, transaction.id)],
                    'date': transaction.date,
                    'amount': transaction.amount,
                })
            # Create the line
            lines |= self.env['account.bank.statement.line'].create(vals)
        return lines

    @api.multi
    def create_bank_statement(self):
        """
        Create / update existing bank statements to add bank statement lines for each transactions in self
        and optionally auto-reconcile the new lines
        created for original transaction or disbursement transaction
        :return: None
        """
        # Prepare two record-sets for newly created statements and lines
        lines_to_skip = created_lines = self.env['account.bank.statement.line']
        statements = self.env['account.bank.statement']

        # Create mapping based on merchant
        transactions_by_account = {}
        for transaction in self:
            account = transaction.merchant_account_id
            transactions_by_account.setdefault(account, self.env['braintree.transaction'])
            transactions_by_account[account] |= transaction

        for m_account, transactions in transactions_by_account.items():
            # Filter out transactions to settle
            transactions_to_settle = transactions.filtered(
                lambda t: not t.bank_statement_line_id and t.status == 'settled')
            # Filter out transactions to disburse
            transactions_to_disburse = transactions.filtered(
                lambda t: not t.disbursement_bank_statement_line_id and t.is_disbursed)
            # Make a data set with two values, second one represents disbursement_mode
            data_set = [(transactions_to_disburse, True), (transactions_to_settle, False)]
            # Loop through account transactions
            for a_transactions, disbursement_mode in data_set:
                # Get date key based on the mode and loop through them
                transaction_date_key = 'disbursement_date' if disbursement_mode else 'date'
                # Make transaction mapping by date key
                transactions_by_date = {}
                for transaction in a_transactions:
                    # Get date value based on a key
                    date_value = getattr(transaction, transaction_date_key)
                    transactions_by_date.setdefault(date_value, self.env['braintree.transaction'])
                    transactions_by_date[date_value] |= transaction

                # Loop through day transactions
                for date, d_transactions in transactions_by_date.items():
                    # Search for corresponding statement
                    statement = statements.search([
                        ('journal_id', '=', m_account.journal_id.id),
                        ('date', '=', date),
                    ])
                    # Reset state to draft if it exists, otherwise create it
                    if statement.state == 'confirm':
                        statement.write({'state': 'open'})
                    if not statement:
                        statement = statements.create({
                            'date': date, 'journal_id': m_account.journal_id.id,
                            'name': '/', 'sepa_imported': True,
                        })
                    # Add line to statement based on the disbursement mode
                    created_lines |= d_transactions.add_line_to_statement(
                        statement, disbursement_mode=disbursement_mode
                    )
                    statements |= statement

        if created_lines:
            # Try to normalize the statements in ascending way
            journals = statements.mapped('journal_id')
            self.env['account.bank.statement'].normalize_balances_ascending(
                journal_ids=journals.ids, force_normalization=True
            )
            # Apply journal import rules and try to reconcile newly created lines
            lines_to_skip |= statements.with_context(skip_error_on_import_rule=True).apply_journal_import_rules()
            created_lines.auto_reconcile_with_accounting_entries(lines_to_skip=lines_to_skip)

    # Actions / Buttons -----------------------------------------------------------------------------------------------

    @api.multi
    def action_open_bank_statement(self):
        """Action that opens related bank statement"""
        self.ensure_one()
        return {
            'res_model': 'account.bank.statement',
            'res_id': self.bank_statement_line_id.statement_id.id,
            'type': 'ir.actions.act_window',
            'context': {},
            'view_mode': 'form',
            'view_type': 'form',
            'view_id': self.env.ref('account.view_bank_statement_form').id,
            'target': 'current',
        }

    @api.multi
    def action_open_disbursement_bank_statement(self):
        """Action that opens related disbursement bank statement"""
        self.ensure_one()
        return {
            'res_model': 'account.bank.statement',
            'res_id': self.disbursement_bank_statement_line_id.statement_id.id,
            'type': 'ir.actions.act_window',
            'context': {},
            'view_mode': 'form',
            'view_type': 'form',
            'view_id': self.env.ref('account.view_bank_statement_form').id,
            'target': 'current',
        }

    @api.multi
    def button_update_from_braintree(self):
        """Button method to update a given transaction"""
        self.ensure_one()
        self.api_update_transactions()

    @api.multi
    def button_update_from_braintree_disbursement(self):
        """Button method to update a given transaction"""
        self.ensure_one()
        self.api_update_transactions(disbursement_mode=True)

    # Auxiliary methods -----------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, 'Trans. ' + rec.transaction_id + ' (' + rec.merchant_account_id.name + ')') for rec in self]

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_braintree_transaction_update(self):
        """Cron that updates non-settled / non-disbursed transactions"""
        # Search for non-settled transactions
        base_domain = [('gateway_id.api_state', '=', 'working'), ('gateway_id.initially_authenticated', '=', True)]
        transactions_to_settle = self.search(base_domain + [('status', 'in', UPDATABLE_STATES)])
        if transactions_to_settle:
            transactions_to_settle.api_update_transactions()

        # Search for transactions that need recreation and create bank statements
        transactions_to_create = self.search(
            base_domain + [('status', '=', 'settled'), ('bank_statement_line_id', '=', False)])
        transactions_to_create.create_bank_statement()

        # Search for non disbursed transactions
        transactions_to_disburse = self.search(
            base_domain + [('is_disbursed', '=', False), ('status', 'not in', DECLINED_STATES)]
        )
        if transactions_to_disburse:
            transactions_to_disburse.api_update_transactions(disbursement_mode=True)
