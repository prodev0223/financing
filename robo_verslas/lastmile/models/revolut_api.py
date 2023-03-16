# -*- encoding: utf-8 -*-
import json
import requests
import logging
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)

KEY_SIZE = 1024
REVOLUT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


class RevolutApi(models.Model):
    _inherit = 'revolut.api'

    api_url = fields.Char(string='API URL', required=True)
    api_username = fields.Char(string='API Username', required=True)
    api_password = fields.Char(string='API Password', required=True)

    @api.multi
    def name_get(self):
        return [(rec.id, 'Revolut API (%s)' % rec.api_username) for rec in self]

    @api.multi
    def _get_authorization_header(self):
        self.ensure_one()
        return {'Authorization': 'Basic ' + ':'.join((self.api_username, self.api_password)).encode('base64')[:-1]}

    @api.multi
    def _get_url(self):
        self.ensure_one()
        return self.api_url

    @api.multi
    def _send_request(self, app, params=None):
        """
        Query the LastMile Gateway API for Revolut

        :param app: describe the Revolut API we're reaching. Options are: 'accounts', 'accounts/<id>', 'transactions',
                    'transaction/<id>', 'counterparties', 'counterparty/<id>', where id is the internal revolut ID (stored in uuid fields in Odoo)
        :param params: dict of parameters passed to the Revolut endpoint, as per Revolut Business API documentation

        :returns: the response from Revolut API as a list of dict
        """
        self.ensure_one()
        headers = self._get_authorization_header()
        headers.update({'content-type': 'application/json; charset=utf-8'})
        url = self._get_url()
        payload = {
            'app': app,
            'params': params or {},
        }
        try:
            response = requests.post(url=url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            raise exceptions.UserError(_('HTTP error %s occurred when connecting to LastMile API') % http_err)
        except:
            raise exceptions.UserError(_('Unknown error occurred when connecting to LastMile API'))

        if response.status_code == 204:
            raise exceptions.UserError(_('Receive empty response from LastMile API'))

        try:
            result = response.json()
        except Exception:
            raise exceptions.UserError(_('Content is not JSON'))

        status = result.get('status')
        if not status:
            raise exceptions.UserError(_('\'status\' was not provided in the response by LastMile API'))
        if status == 'error' or status != 'ok':
            raise exceptions.UserError(_('The Revolut API request failed with the following error: %s')
                                       % result.get('reason', 'Error not provided'))
        return result.get('data', [])

    @api.multi
    def get_transaction(self, uuid):
        """
        Request Get transaction/<id> to API

        :param uuid: string, transaction id in the revolut system
        :returns: a dict containing the detailed information about the transaction
        """
        self.ensure_one()
        return self._send_request(app='transaction/{}'.format(uuid))

    @api.multi
    def _get_transactions(self, data=None):
        """
        Request Get transactions to API (Overridden from base to use LastMile gateway)

        :param data: dict containing the optionnal request parameters:
                - from: filter on created_at, timestamp in ISO 6801
                - to: filter on created_at, timestamp in ISO 6801
                - count: maximum number of transactions (max 1000, default if not specified: 100)
                - type: the transaction type, one of atm, card_payment, card_refund, card_chargeback, card_credit,
                        exchange, transfer, loan, fee, refund, topup, topup_return, tax, tax_refund
                - counterparty: a counterparty_id
        :returns: a list of transaction values in dicts
        """
        self.ensure_one()
        return self._send_request(app='transactions', params=data)

    @api.multi
    def get_account(self, uuid):
        """
        Request GET account/<id> to API

        :param uuid: string, account id in the revolut system
        :returns: a dict containing the detailed information about the transaction
        """
        self.ensure_one()
        return self._send_request(app='accounts/{}'.format(uuid))

    @api.multi
    def _get_accounts(self):
        """
        Request GET accounts to API

        :returns: a list of accounts values in dicts
        """
        self.ensure_one()
        return self._send_request(app='accounts')

    @api.multi
    def _process_leg_data(self, legs):
        """
        Process leg data
        :param legs:
        :return: True if processed, False if not
        """
        self.ensure_one()
        try:
            n_legs = len(legs)
        except:
            n_legs = 0
        if n_legs != 1:
            # For Lastmile, we ignore all internal transfers
            return False
        else:
            return super(RevolutApi, self)._process_leg_data(legs)

    @api.multi
    def _save_transactions(self, data):
        return super(RevolutApi, self.with_context(importing_to_journal=False))._save_transactions(data)


RevolutApi()
