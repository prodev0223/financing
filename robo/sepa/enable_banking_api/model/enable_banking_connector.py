# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, tools, fields, exceptions, _
from .. import enable_banking_tools as eb
from datetime import datetime


class EnableBankingConnector(models.Model):
    _name = 'enable.banking.connector'
    _description = 'Model that emulates separate integration for a specific bank'
    _inherit = 'mail.thread'

    @api.model
    def _default_country_id(self):
        """Returns company country as default country ID"""
        return self.env.user.company_id.country_id

    # Identifier fields
    name = fields.Char(string='API Name', required=True)
    api_code = fields.Char(string='API Code', required=True)
    bank_id = fields.Many2one('res.bank', string='Bank')
    # All of the other banks that share the same name but are not main branches
    related_bank_ids = fields.Many2many('res.bank', string='Related banks')

    country_id = fields.Many2one(
        'res.country', string='Country',
        required=True, default=_default_country_id
    )
    configuration_id = fields.Many2one(
        'enable.banking.configuration',
        string='Enable banking configuration'
    )
    # API state/info fields
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('working', 'API is working'),
        ('expired', 'API session is expired'),
    ], string='State', default='not_initiated',
        track_visibility='onchange'
    )
    last_api_error_message = fields.Text(string='API error message')
    # Session fields
    valid_to = fields.Datetime(string='Session validity end date', track_visibility='onchange')
    session_id = fields.Char(string='Session ID', track_visibility='onchange')
    latest_state_vector = fields.Char(string='State initialization vector')
    last_session_user_id = fields.Many2one('res.users', string='Authenticated user')

    # Allowed PSU types (Set via API)
    business_psu = fields.Boolean(string='Business')
    personal_psu = fields.Boolean(string='Personal')
    # Selected PSU type
    psu_type = fields.Selection(
        [('business', 'Business'), ('personal', 'Personal')],
        string='PSU Type', default='business'
    )
    # Related accounts
    banking_account_ids = fields.One2many(
        'enable.banking.account', 'bank_connector_id',
        string='Banking accounts',
    )
    # Misc fields
    display_name = fields.Char(compute='_compute_display_name', string='Name')
    has_accounts_to_configure = fields.Boolean(compute='_compute_has_accounts_to_configure')
    active = fields.Boolean(string='Active')  # Intentionally defaults to False
    authorization_failure = fields.Boolean(string='Authorization failure', track_visibility='onchange')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('bank_id', 'country_id')
    def _compute_display_name(self):
        """Computes display name - bank name + country code"""
        for rec in self:
            rec.display_name = '{} [{}]'.format(rec.bank_id.name or _('Not-configured'), rec.country_id.code)

    @api.multi
    @api.depends('banking_account_ids.active', 'banking_account_ids.journal_id')
    def _compute_has_accounts_to_configure(self):
        """Check whether there's any accounts that need configuration (journal relation)"""
        for rec in self:
            rec.has_accounts_to_configure = any(
                not x.journal_id and x.active for x in rec.banking_account_ids
            )

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('psu_type')
    def _check_psu_type(self):
        """Ensures that selected PSU type is allowed by the bank"""
        for rec in self:
            if rec.psu_type == 'personal' and not rec.personal_psu or \
                    rec.psu_type == 'business' and not rec.business_psu:
                raise exceptions.ValidationError(_('Selected PSU type is not allowed by the bank'))

    @api.multi
    @api.constrains('bank_id', 'active')
    def _check_bank_id(self):
        """Ensures that connector could not be activated without the set bank record"""
        for rec in self:
            if rec.active and not rec.bank_id:
                raise exceptions.ValidationError(_('You cannot enable a connector without a bank'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def authenticate_bank_connector(self):
        """
        Gets authentication URL for current bank connector,
        then redirect user to oAuth endpoint.
        :return: JS URL action (dict)
        """
        self.ensure_one()
        response_data = self.env['enable.banking.api.base'].api_authorize_bank_connector(
            connector=self)
        authentication_url = response_data.get('url')
        if not authentication_url:
            raise exceptions.ValidationError(
                _('You cannot execute this action if no authentication URL is set')
            )
        # Write session user ID here, since later methods are called
        # from different systems (website/internal) with SUPER_UID
        self.write({'last_session_user_id': self.env.user.id, })
        return {
            'type': 'ir.actions.act_url',
            'url': authentication_url,
            'target': 'new',
        }

    @api.multi
    def initiate_user_session(self, session_code):
        """
        Used to initiate new user session with received code
        method is called from a controller on callback redirect
        """
        self.ensure_one()
        self.env['enable.banking.api.base'].api_initiate_user_session(
            connector=self, session_code=session_code,
        )
        # Relate account journals for current accounts
        self.banking_account_ids.relate_account_journals()
        # Execute initial balance fetch
        self.banking_account_ids.fetch_account_balance()

    @api.multi
    def create_banking_accounts(self, accounts_data):
        """
        Creates enable.banking.account records based
        on the data received via api for current connector.
        If duplicate external ID is found for the same connector
        creation is skipped.
        """
        self.ensure_one()
        eb_account_obj = self.sudo().env['enable.banking.account'].with_context(active_test=False)
        for account_data in accounts_data:
            # Historic currencies that are not used anymore like 'LTL' are still passed.
            # If we receive either of those currencies we just skip
            currency = self.env['res.currency'].search([('name', '=', account_data['currency'])], limit=1)
            if not currency:
                continue
            external_id = account_data['uid']
            # Firstly execute simple external ID check
            if eb_account_obj.search_count([('bank_connector_id', '=', self.id), ('external_id', '=', external_id)]):
                continue
            # Secondly - external ID is generated per session, thus same accounts will have different ext IDs on
            # re-authentication, thus we first try to find them by connector, IBAN and currency
            account_iban = account_data['account_id']['iban']
            # Search for the account, and update external ID if we find one
            e_banking_account = eb_account_obj.search([
                ('bank_connector_id', '=', self.id),
                ('currency_id', '=', currency.id),
                ('account_iban', '=', account_iban),
            ])
            if e_banking_account:
                e_banking_account.write({'external_id': external_id})
            else:
                # Create banking account otherwise
                eb_account_obj.create({
                    'external_id': external_id,
                    'currency_id': currency.id,
                    'bank_connector_id': self.id,
                    'account_iban': account_data['account_id']['iban'],
                })

    @api.model
    def prepare_connector_creation_data(self):
        """
        Calls the API endpoint and gathers connector data
        into a list of dicts, suitable for creation.
        :return: connector data (list)
        """
        connectors = []
        # Get all of the specified connector names and call the endpoint
        # to fetch connector data, create them.
        response_data = self.env['enable.banking.api.base'].api_get_bank_list()
        country = self._default_country_id()
        for connector_data in response_data['aspsps']:
            # We mark connectors as not 'active', i.e. those that are not supported, specified in the code.
            # Non company country connectors are skipped altogether for now.
            if connector_data['country'] != country.code:
                continue
            # Prepare connector creation values
            connector_vals = {
                'name': connector_data['name'],
                'business_psu': 'business' in connector_data['psu_types'],
                'personal_psu': 'personal' in connector_data['psu_types'],
            }
            connectors.append((0, 0, connector_vals))
        return connectors

    @api.multi
    def post_custom_message(self, post_data):
        """
        Posts a message to enable.banking.connector record.
        Method is meant to be overridden with message post
        directly to the client.
        :return: None
        """
        self.ensure_one()
        # Copy data dict and pop partner_ids. Not popped from the original parameter
        # since the field is used in overridden method.
        data = post_data.copy()
        data.pop('partner_ids')
        self.message_post(**data)

    @api.multi
    def is_valid(self):
        """Checks whether connector's session is still valid"""
        self.ensure_one()
        is_valid = False
        if self.valid_to and self.session_id:
            c_date_dt = datetime.utcnow()
            expiry_date_dt = datetime.strptime(self.valid_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if expiry_date_dt > c_date_dt:
                is_valid = True
        return is_valid

    @api.multi
    def reset_connectors_sessions(self):
        """Resets all related session values"""
        self.write({'session_id': False, 'valid_to': False, 'api_state': 'not_initiated', })

    @api.multi
    def relate_to_corresponding_banks(self):
        """
        Relates res.bank records to newly configured connectors.
        Connectors that have corresponding journals in the system are set to active as well
        """
        for rec in self:
            # Global API codes of the connector
            bic_codes = eb.CONNECTOR_BANK_BIC_MAPPING.get(rec.api_code)
            if bic_codes:
                # Get bic codes from the relation dict
                main_bic = bic_codes.get('bic_code')
                related_codes = bic_codes.get('related_bic_codes', [])
                related_banks = self.env['res.bank']
                # If no corresponding bank is found, skip connectors relation
                main_bank = related_banks.search(
                    [('bic', '=', main_bic)], limit=1, order='create_date asc')
                if not main_bank:
                    continue
                # Search for related banks
                if related_codes:
                    related_banks = related_banks.search([('bic', 'in', related_codes)])
                # Prepare the main write values
                values = {
                    'bank_id': main_bank.id,
                    'related_bank_ids': [(4, x.id) for x in related_banks],
                }
                # Gather total BIC codes
                total_bic_codes = [main_bic] + related_codes
                # Activate the connector if there's any journals in the system with main or related banks.
                # Search criteria is done via bic, so all of the branches are included as well.
                if self.env['account.journal'].search_count(
                        [('bank_id.bic', 'in', total_bic_codes), ('type', '=', 'bank')]):
                    values['active'] = True
                # Write the values
                rec.write(values)

    # Buttons ---------------------------------------------------------------------------------------------------------

    @api.multi
    def button_relate_account_journals(self):
        """
        Relates (creates or links) account
        journals to current connector's banking accounts
        """
        self.ensure_one()
        self.banking_account_ids.relate_account_journals()

    @api.multi
    def button_fetch_accounts_balances(self):
        """
        Relates (creates or links) account
        journals to current connector's banking accounts
        """
        self.ensure_one()
        self.banking_account_ids.fetch_account_balance()

    @api.multi
    def button_terminate_connector_session(self):
        """
        Calls API to terminate current session for the connector.
        If call is successful, connector is marked as not_initiated
        """
        self.ensure_one()
        # Check if session ID exists
        if not self.session_id:
            raise exceptions.ValidationError(
                _('Current connector does not have an active session that can be terminated')
            )
        # Call the endpoint to terminate the session
        self.env['enable.banking.api.base'].api_terminate_user_session(connector=self)
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    # Model methods ---------------------------------------------------------------------------------------------------

    @api.model
    def check_connector_state_vector(self, state_vector):
        """Check whether there's a connector with a passed state vector. Method is called from internal"""
        return self.search_count([('latest_state_vector', '=', state_vector)])

    @api.model
    def get_integrated_bic_codes(self, connectors=None):
        """
        Returns set of bank bic codes that have working connectors.
        Relevant in cases where bank has multiple branches
        :param connectors: BIC codes (set)
        """
        if connectors is None:
            connectors = self.search([('api_state', '=', 'working')])
        return set(connectors.mapped('bank_id.bic') + connectors.mapped('related_bank_ids.bic'))

    @api.model
    def activate_connectors(self, journal):
        """
        Activates connectors that have integrated bic
        which corresponds to passed account journal record
        :param journal: account.journal (record)
        :return: None
        """
        # Check whether passed journal has related bank
        if journal.bank_id:
            # Search for inactive connectors that have related bank records. If current journal
            # matches any of the connectors integrated bic codes, filter them out and set as active
            connectors = self.with_context(active_test=False).search(
                [('active', '=', False), ('bank_id', '!=', False)]).filtered(
                lambda x: journal.bank_id.bic in x.get_integrated_bic_codes(x)
            )
            connectors.write({'active': True})

    @api.model
    def get_configured_accounts(self):
        """
        Returns all Enable Banking accounts that have working connectors
        and are configured - activated with related account journal
        """
        connectors = self.search([('api_state', '=', 'working')])
        # Get all of the activated banking accounts
        e_banking_accounts = connectors.mapped('banking_account_ids').filtered(
            lambda x: x.journal_id
        )
        return e_banking_accounts

    # Cron jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_check_session_ttl(self):
        """
        Checks time to live of connector sessions, updates API states
        if sessions are expired and sends message to the
        company manager/initiation user regarding session re-initiation.
        """
        # Search for connectors with initially authenticated session
        connectors = self.env['enable.banking.connector'].search(
            [('session_id', '!=', False), ('valid_to', '!=', False)])
        ceo_partner = self.env.user.company_id.vadovas.user_id.partner_id
        c_date_dt = datetime.utcnow()
        # Try to fetch expired connector warning before hours, defaults to 24
        expired_connector_warning_hours = self.env['ir.config_parameter'].get_param(
            'enable_banking_expired_connector_warning_hours')
        try:
            expired_connector_warning_hours = int(expired_connector_warning_hours)
        except (ValueError, AttributeError):
            expired_connector_warning_hours = 24
        # Loop through connectors and check the
        for connector in connectors:
            # Get connectors expiry date
            expiry_date_dt = datetime.strptime(connector.valid_to, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            # Calculate time delta in hours
            delta = expiry_date_dt - c_date_dt
            # P3:DivOK
            delta_hours = (delta.days * 1440 + delta.seconds // 60) // 60
            # If delta is less than/equal to zero, clear the session ID and set API state to expired
            if delta_hours <= 0:
                connector.write({'session_id': False, 'valid_to': False, 'api_state': 'expired'})
            # If delta is less than x hours, send a message.
            # Message is sent two times at max, since session_id is cleared on negative delta.
            if delta_hours <= expired_connector_warning_hours:
                # Either take the partner from connector or use CEO partner
                partner = connector.last_session_user_id.partner_id or ceo_partner
                # If connector still has the session ID -- message is a warning, otherwise expiry info
                inner_message = _('will expire after {} hours').format(delta_hours) \
                    if connector.session_id else _('has expired')
                # Build message body
                base_body = _(
                    'Warning! API access for Enable Banking connector - [{}] {}. '
                    'Please re-authenticate the access').format(
                    connector.display_name, inner_message,
                )
                post_data = {
                    'body': base_body,
                    'subject': _('Enable Banking API - {} - {}').format(connector.display_name, inner_message),
                    'partner_ids': partner.ids,
                }
                # Post the message to connector
                connector.post_custom_message(post_data)
