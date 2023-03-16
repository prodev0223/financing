# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _
from datetime import datetime
import requests
import urllib
import uuid


class AmazonSPRegion(models.Model):
    _name = 'amazon.sp.region'
    _inherit = 'mail.thread'
    _description = '''Model that stores SP API region data'''

    name = fields.Char(string='Name', required=1)
    code = fields.Char(string='Code', required=1)
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('working', 'API is working'),
        ('expired', 'API session is expired'),
    ], string='State', default='not_initiated',
        track_visibility='onchange')
    region_endpoint = fields.Char(string='Region endpoint', required=1)

    # Access token fields
    access_token = fields.Char(string='Access token')
    refresh_token = fields.Char(string='Refresh token')
    restricted_data_token = fields.Char(string='Restricted data token')
    access_token_expiry_date = fields.Datetime(string='Access Token TTL')

    marketplace_ids = fields.One2many('amazon.sp.marketplace', 'region_id', string='Marketplaces')
    configuration_id = fields.Many2one('amazon.sp.configuration')

    # Information on last authentication action
    last_api_error_message = fields.Text(string='Latest error message')
    last_state_vector = fields.Char(string='Latest session state vector')
    last_session_user_id = fields.Many2one('res.users', string='Authenticated user')

    @api.multi
    def authenticate_region_api(self):
        """
        Gets authentication URL for current bank connector,
        then redirect user to oAuth endpoint.
        :return: JS URL action (dict)
        """
        self.ensure_one()

        if not self.configuration_id.check_configuration(ignore_api_state=True):
            raise exceptions.ValidationError(
                _('Amazon SP-API settings are not configured. Contact administrators')
            )

        activated_marketplaces = self.marketplace_ids.filtered(lambda x: x.activated)
        if not activated_marketplaces:
            raise exceptions.ValidationError(
                _('You must activate at least one marketplace in order to authenticate the region')
            )

        # Amazon authorization is done using specific marketplace's URL, however, when user
        # authenticates one marketplace, whole region becomes available for the API calls.
        default_marketplace = activated_marketplaces[0]

        # Compose redirect_url URL
        redirect_url = self.configuration_id.get_redirect_url()

        # Compose state vector
        state_init_vector = '{}__{}__{}'.format(self.env.cr.dbname, str(uuid.uuid1()), self.id)
        self.write({
            'last_state_vector': state_init_vector,
            'last_session_user_id': self.env.user.id,
        })
        application_id = self.configuration_id.sudo().application_key
        # Build request data that is passed in the URL
        request_data = {
            'application_id': application_id,
            'state': state_init_vector,
            'redirect_uri': redirect_url,
            'version': 'beta',
        }
        # Prepare base authorization URL
        auth_url = '{}/apps/authorize/consent?'.format(
            default_marketplace.marketplace_endpoint, application_id,
        )
        # Build data part of the URL
        data_url = '&'.join('%s=%s' % (k, v) for k, v in request_data.items())
        auth_url = auth_url + data_url

        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'new',
        }

    @api.multi
    def action_open_marketplaces(self):
        """
        Returns action that opens SP-API marketplace tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_marketplace').read()[0]
        action['domain'] = [('id', 'in', self.marketplace_ids.ids)]
        return action

    @api.multi
    def check_token_ttl(self):
        """
        Checks whether current access data token is still valid
        :return: True if valid otherwise False
        """
        self.ensure_one()
        if self.access_token and self.access_token_expiry_date:
            c_time = datetime.utcnow()
            # Never more than an hour from now
            exp_date_dt = datetime.strptime(
                self.access_token_expiry_date, tools.DEFAULT_SERVER_DATETIME_FORMAT
            )
            # If current token is valid for next 10 minutes, return it as valid
            if (exp_date_dt - c_time).total_seconds() > 600:
                return True
        return False
