# -*- coding: utf-8 -*-
from odoo import api, exceptions, fields, models, _
from datetime import datetime
import braintree
import logging

_logger = logging.getLogger(__name__)


class BraintreeGateway(models.Model):
    _name = 'braintree.gateway'
    _inherit = 'mail.thread'

    @api.model
    def _default_date_start(self):
        """Return default date - utc-now"""
        return datetime.utcnow()

    name = fields.Char(string='Gateway name', required=True)

    # Main gateway fields
    merchant_id = fields.Char(
        string='Merchant ID', required=True,
        inverse='_set_initially_authenticated',
    )
    public_key = fields.Char(
        string='Public key', required=True,
        inverse='_set_initially_authenticated',
    )
    private_key = fields.Char(
        string='Private key', required=True,
        inverse='_set_initially_authenticated',
    )

    # Related accounts / transactions
    merchant_account_ids = fields.One2many('braintree.merchant.account', 'gateway_id')
    transaction_ids = fields.One2many('braintree.transaction', 'gateway_id')

    # Configuration fields
    account_prefix = fields.Char(string='Main account prefix', required=True, default='27')
    environment = fields.Selection(
        [('production', 'Production'),
         ('sandbox', 'Sandbox')],
        string='Environment', required=True,
        default='production',
    )
    allowed_reconciliation_difference = fields.Float(
        string='Allowed reconciliation difference',
        help='Maximum price mismatch allowed for automatic reconciliation',
    )
    gateway_init_date = fields.Datetime(
        string='Threshold fetch date', required=True,
        default=_default_date_start,
    )
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('working', 'API is working'),
    ], string='API state', default='not_initiated')
    forced_partner_id = fields.Many2one('res.partner', string='Forced partner')

    # Indicates whether API was initially authenticated manually
    initially_authenticated = fields.Boolean(string='Initially authenticated')

    # Inverses --------------------------------------------------------------------------------------------------------

    @api.multi
    def _set_initially_authenticated(self):
        """If any of the API keys change, reset initially authenticated field, and API state"""
        self.filtered('initially_authenticated').write({
            'api_state': 'not_initiated',
            'initially_authenticated': False,
        })

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('account_prefix')
    def _check_account_prefix(self):
        """Ensure that account prefix is made from digits"""
        for rec in self:
            if rec.account_prefix and not rec.account_prefix.isdigit():
                raise exceptions.ValidationError(_('Account prefix can only contain digits!'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def initiate_api(self):
        """Used to initially test API to mark gateway as authenticated"""
        self.ensure_one()
        try:
            # Try to initialize current gateway
            gateway = self.api_init_gateway()
            # Try to fetch the accounts, we would get an authentication error here
            next(iter(gateway.merchant_account.all().merchant_accounts))
        except Exception as exc:
            error_message = 'Braintree gateway error - {}'.format(exc.args[0] if exc.args else exc.__repr__())
            _logger.info(error_message)
            values = {'api_state': 'failed'}
            self.message_post(body=error_message)
        else:
            values = {
                'api_state': 'working',
                'initially_authenticated': True,
            }
        # Write corresponding values to gateway
        self.write(values)

    @api.multi
    def api_fetch_merchant_accounts(self):
        """
        API Method //
        Fetch all information about merchant accounts and creates them if needed
        :return: None
        """
        self.ensure_one()
        if not self.check_api():
            return

        # Initiate the gateway
        gateway = self.api_init_gateway()
        result = gateway.merchant_account.all()
        # Loop through remote accounts and either create or update them
        for remote_merchant_account in result.merchant_accounts:
            merchant_account_id = remote_merchant_account.id
            merchant_account = self.env['braintree.merchant.account'].search([('name', '=', merchant_account_id)])
            if not merchant_account:
                currency = self.env['res.currency'].search([('name', '=', remote_merchant_account.currency_iso_code)])
                # Prepare the account values
                vals = {
                    'name': merchant_account_id,
                    'currency_id': currency.id,
                    'status': remote_merchant_account.status,
                    'gateway_id': self.id,
                }
                merchant_account = self.env['braintree.merchant.account'].create(vals)
            merchant_account.update_merchant_account(remote_merchant_account)

    @api.multi
    def api_init_gateway(self):
        """
        API Method //
        Returns a BraintreeGateway object to perform API queries
        """
        self.ensure_one()
        # Check the environment that is set on specific gateway
        environment = braintree.Environment.Production \
            if self.environment == 'production' else braintree.Environment.Sandbox
        return braintree.BraintreeGateway(
            braintree.Configuration(
                environment=environment,
                merchant_id=self.sudo().merchant_id,
                public_key=self.sudo().public_key,
                private_key=self.sudo().private_key,
            )
        )

    @api.multi
    def check_api(self):
        """
        Checks whether current gateway is working,
        update it's state and post the message if it's not.
        :return: True/False
        """
        self.ensure_one()
        try:
            # Try to initialize current gateway
            gateway = self.api_init_gateway()
            # Try to fetch the accounts, we would get an authentication error here
            next(iter(gateway.merchant_account.all().merchant_accounts))
        except Exception as exc:
            error_message = 'Braintree gateway error - {}'.format(exc.args[0] if exc.args else exc.__repr__())
            _logger.info(error_message)
            self.write({'api_state': 'failed'})
            self.message_post(body=error_message)
            return False
        return True

    # Actions ---------------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_transactions(self):
        """
        Opens a view to all transactions from that gateway
        :return: action (dict)
        """
        self.ensure_one()
        action = self.env.ref('sepa.braintree_transaction_action')
        action = action.read()[0]
        action['domain'] = [('gateway_id', '=', self.id)]
        action['view_mode'] = 'tree'
        return action

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """ Checks that no transaction is linked to the gateway before allowing to delete """
        if any(rec.transaction_ids for rec in self):
            raise exceptions.UserError(_('You cannot delete this gateway because there are linked transactions.'))
        self.mapped('merchant_account_ids').unlink()
        return super(BraintreeGateway, self).unlink()
