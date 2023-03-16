# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, api, exceptions, _, tools
from .. import paysera_tools as pt
from ... import api_bank_integrations as abi
from datetime import datetime


class PayseraConfiguration(models.Model):
    """
    Transient model that allows user to configure
    Paysera API settings.
    """
    _name = 'paysera.configuration'
    _inherit = ['mail.thread']

    # Main auth values (Always provided by Robolabs)
    paysera_api_client_id = fields.Char(string='Paysera client ID', groups='base.group_system')
    paysera_api_mac_key = fields.Char(string='Paysera MAC key', groups='base.group_system')

    # Transfer API keys (Provided by client itself)
    paysera_tr_api_client_id = fields.Char(string='Paysera client ID')
    paysera_tr_api_mac_key = fields.Char(string='Paysera MAC key')

    # Tokens
    access_token = fields.Char(string='API Access token')
    access_token_mac_key = fields.Char(string='API Access token MAC key')
    token_type = fields.Char(string='API Token type')
    expires_on = fields.Datetime(string='API Token expiry date')
    refresh_token = fields.Char(string='API Refresh token')
    paysera_user_id = fields.Integer(string='Paysera user ID')

    # Other fields
    # Initially authenticated is used for offline scopes -- some actions
    # require you to initially authenticate, and after that, expired keys
    # will also work.
    initially_authenticated = fields.Boolean(string='Authentication was already granted once')
    expired_keys = fields.Boolean(string='Expired API keys')
    user_id = fields.Many2one('res.users', string='User that granted the authorization')
    paysera_wallet_ids = fields.One2many('paysera.wallet', 'paysera_configuration_id', string='Paysera wallets')
    failed_wallets = fields.Boolean(compute='_compute_failed_wallets')
    api_mode = fields.Selection([('not_initiated', 'Not initiated'),
                                 ('partial_integration', 'Partial integration'),
                                 ('full_integration', 'Full integration'),
                                 ], string='API Mode', default='not_initiated')
    api_state = fields.Selection([('not_initiated', 'API is Disabled'),
                                  ('failed', 'Failed to configure the API'),
                                  ('expired_keys', 'API keys are expired'),
                                  ('working', 'API is working'),
                                  ], string='State', default='not_initiated')

    # External signing fields
    allow_external_signing = fields.Boolean(
        string='Enable transaction signing', groups='base.group_system', inverse='_set_allow_external_signing')
    external_signing_daily_limit = fields.Float(
        string='Daily transaction signing limit', groups='base.group_system', inverse='_set_allow_external_signing')
    external_signing_daily_limit_residual = fields.Float(
        string='Daily transaction signing limit residual', groups='base.group_system')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_failed_wallets(self):
        """Checks whether there are any failed wallets"""
        for rec in self:
            rec.failed_wallets = any(
                x.state == 'configuration_error' and x.activated for x in rec.paysera_wallet_ids
            )

    @api.multi
    def _set_allow_external_signing(self):
        """
        Inverse //
        Set external signing daily limit and residual
        based on whether external signing was enabled
        :return: None
        """
        for rec in self:
            if rec.allow_external_signing and tools.float_is_zero(
                    rec.external_signing_daily_limit, precision_digits=2):
                raise exceptions.ValidationError(
                    _('It is mandatory to set a daily amount limit if you want to enable transaction signing'))
            current_residual = rec.external_signing_daily_limit
            if not tools.float_is_zero(rec.external_signing_daily_limit_residual, precision_digits=2):
                current_residual = min([rec.external_signing_daily_limit_residual, rec.external_signing_daily_limit])
            rec.external_signing_daily_limit_residual = current_residual

    # Main Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def deactivate_api(self):
        """
        Method used to deactivate API without
        archiving the related journal records
        :return: None
        """
        self.ensure_one()
        self.write({'api_state': 'not_initiated'})

    @api.multi
    def test_api(self):
        """
        Method used to test whether initially passed MAC and client_id are correct
        and whether client can proceed with further API configurations.
        :return: None
        """
        self.ensure_one()
        if self.api_mode == 'full_integration':
            successful_call, response_data = self.env['paysera.api.base'].call(
                action='test_api',
                extra_data={'object_id': pt.SIMULATED_TRANSFER_ID},
                forced_client_id=self.paysera_tr_api_client_id,
                forced_mac_key=self.paysera_tr_api_mac_key
            )
            if not successful_call:
                raise exceptions.UserError(response_data.get('error', str()))

    @api.multi
    def reset_api_settings(self):
        """
        Method that is used to reset all API settings,
        used when main wallet holder is changed.
        :return: None
        """
        self.ensure_one()
        self.write({
            'access_token': False,
            'access_token_mac_key': False,
            'token_type': False,
            'expires_on': False,
            'refresh_token': False,
            'paysera_user_id': False,
            'initially_authenticated': False,
            'expired_keys': False,
            'user_id': False,
            'api_state': 'not_initiated',
        })
        # Delete all related wallets in the system
        self.env['paysera.wallet'].search([]).sudo().unlink()
        self.env['paysera.wallet.iban'].search([]).sudo().unlink()

    @api.multi
    def initiate_oauth(self):
        """
        Initiate oAuth by redirecting the user to Paysera system for authentication.
        User must authenticate the scopes that are mandatory for Paysera integration.
        :return: URL JS action (dict)
        """
        self.ensure_one()
        # Ensure that only CEO initiates the o-auth (Admin user is ignored)
        if self.env.user.company_id.vadovas.user_id.id != self.env.user.id \
                and not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Only company CEO can initiate the API!'))

        if self.api_mode not in ['partial_integration', 'full_integration']:
            raise exceptions.UserError(_('You have to select an API mode to proceed'))

        self.check_key_constraints()

        # Test API connection before each manual action
        self.test_api()

        # if API is successfully tested, write current user
        self.with_context(force_write=True).write({'user_id': self.env.user.id})

        # Compose oAuth URL
        base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        redirect_url = '%s/web/paysera_configuration/%s' % (base_url, self.id)

        scopes = '%20'.join(pt.RESOURCE_SCOPES)
        oauth_url = 'https://www.paysera.com/frontend/oauth?response_type=code' \
                    '&client_id={}&redirect_uri={}&scope={}'.format(
                     self.sudo().paysera_api_client_id, redirect_url, scopes)

        return {
            'type': 'ir.actions.act_url',
            'url': oauth_url,
            'target': 'self',
        }

    @api.multi
    def get_access_tokens(self, paysera_code):
        """
        Method called ONLY on redirect from a controller -
        Fetches access tokens after confirmation in Paysera
        GUI. Special code is provided which is used in token
        fetching afterwards. After this action all of the
        wallets are re-initiated.
        :param paysera_code: Paysera provided code (str)
        :return: None
        """
        self.ensure_one()
        base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        redirect_url = '%s/web/paysera_configuration/%s' % (base_url, self.id)

        successful_call, response_data = self.env['paysera.api.base'].call(
            action='fetch_tokens',
            extra_data={'code': paysera_code, 'redirect_uri': redirect_url, 'grant_type': 'authorization_code'},
            forced_client_id=self.sudo().paysera_api_client_id,
            forced_mac_key=self.sudo().paysera_api_mac_key
        )
        self.write_access_keys(successful_call, response_data)

        # Always re-initiate wallets on token receive
        self.env['paysera.api.base'].api_initiate_wallets()

    @api.multi
    def get_wallets(self):
        """
        Method that is called from the form view.
        Re-initiates Paysera wallets manually.
        :return: None
        """
        self.ensure_one()
        self.check_key_constraints()

        # Test API connection before each manual action
        self.test_api()
        self.env['paysera.api.base'].api_initiate_wallets(raise_exception=True)

    # Auxiliary Methods -----------------------------------------------------------------------------------------------

    @api.multi
    def check_key_constraints(self):
        """
        Check API key constraints
        :return: None
        """
        if self.api_mode == 'full_integration' and (
                not self.paysera_tr_api_client_id or not self.paysera_tr_api_mac_key):
            raise exceptions.UserError(_('Both API client ID and MAC key must be passed!'))

        if not self.sudo().paysera_api_client_id or not self.sudo().paysera_api_mac_key:
            raise exceptions.UserError(_('Missing configuration from Robolabs, contact administrators!'))

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Paysera configuration')) for x in self]

    @api.multi
    def write_access_keys(self, successful_call, response_data, refresh=False):
        """
        Method that writes fetched access keys
        :param successful_call: indicates whether call was successful (bool)
        :param response_data: response data (dict)
        :param refresh: Indicates whether the action was initial or refresh
        :return: None
        """
        self.ensure_one()
        if successful_call:
            values_to_write = {
                'refresh_token': response_data.get('refresh_token'),
                'access_token': response_data.get('access_token'),
                'token_type': response_data.get('token_type'),
                'access_token_mac_key': response_data.get('mac_key'),
                'api_state': 'working',
                'expired_keys': False,
                'initially_authenticated': True
            }
        else:
            api_state = 'expired_keys' if refresh else 'failed'
            values_to_write = {'api_state': api_state}
        self.with_context(force_write=True).write(values_to_write)

    @api.multi
    def initiate_settings(self):
        """
        Initiate paysera.settings record.
        If settings record exists, return it.
        :return: paysera.settings record
        """
        settings = self.search([])
        if not settings:
            settings = self.create({})
        return settings

    @api.multi
    def create(self, vals):
        """
        Create method override, if settings record already exists,
        do not allow to create another instance
        :param vals: record values
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several Paysera configuration records!'))
        return super(PayseraConfiguration, self).create(vals)

    @api.multi
    def write(self, vals):
        """
        Write method override, do not allow
        the write if api state != 'working'
        :param vals: record values
        :return: super of write method
        """
        check_state = self._context.get('check_state')
        if check_state:
            for rec in self:
                if rec.api_state != 'working':
                    raise exceptions.UserError(_('You cannot store invalid / unverified API keys!'))
                if not rec.paysera_wallet_ids or all(x.state != 'configured' for x in rec.paysera_wallet_ids):
                    raise exceptions.UserError(_('You have to activate/configure at least one wallet!'))
        res = super(PayseraConfiguration, self).write(vals)

        # If checks and write itself are successful, configure the journals
        self.env['api.bank.integrations'].configure_related_bank_journals(abi.PAYSERA)
        return res

    # Cron-jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_clear_external_signing_daily_limit_residual(self):
        """
        Cron-job //
        Method that is used to clear external signing daily limit residual
        amount -- called each night
        :return: None
        """
        configuration = self.search([], limit=1)
        if not configuration:
            return
        date_now_dt = datetime.utcnow()

        latest_signed_export = self.env['bank.export.job'].search(
            [('journal_id.bank_id.bic', '=', abi.PAYSERA), ('e_signed_export', '=', True)],
            order='date_signed desc', limit=1)

        residual_reset = configuration.external_signing_daily_limit
        if not latest_signed_export:
            configuration.write({'external_signing_daily_limit_residual': residual_reset})
        else:
            last_sign_date_dt = datetime.strptime(
                latest_signed_export.date_signed, tools.DEFAULT_SERVER_DATETIME_FORMAT)

            diff = date_now_dt - last_sign_date_dt
            # If latest update was done less than two hours ago
            # we only write half of residual TODO: (Improve this part)
            # P3:DivOK
            if diff.total_seconds() / 3600.0 < 2:
                residual_reset = residual_reset / 2

            configuration.write({'external_signing_daily_limit_residual': residual_reset})
