# -*- encoding: utf-8 -*-
import revolut
from revolut.session import TokenProvider, RenewableSession
import base64
import requests

try:  # pragma: nocover
    from urllib.parse import urljoin, urlencode  # 3.x
except ImportError:  # pragma: nocover
    from urlparse import urljoin  # 2.x
    from urllib import urlencode
import logging
from OpenSSL import crypto
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)

KEY_SIZE = 1024
REVOLUT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
REVOLUT_MAX_TRANSACTIONS_PER_REQUEST = 1000
REVOLUT_DEFAULT_TRANSACTIONS_PER_REQUEST = 100
CRYPTO_CURRENCIES = {
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'XRP': 'Ripple',
    'ADA': 'Cardano',
}


class RevolutApi(models.Model):
    _name = 'revolut.api'
    _description = 'Connecting to Revolut Business API'

    name = fields.Char(string='Pavadinimas', compute='_compute_name')
    x509_public_key_display = fields.Text(compute='_compute_x509_public_key')
    private_key = fields.Text(compute='_compute_private_key', groups='base.group_system')
    jwt = fields.Text(compute='_compute_jwt', groups='base.group_system')
    callback_address = fields.Char(string='OAuth nukreipimo URI', compute='_compute_callback_address')
    auth_code = fields.Char(string='OAuth kodas')
    client_id = fields.Char(string='Revolut App client ID', inverse='_set_client_id')
    access_token = fields.Char(string='Prieigos raktas')
    refresh_token = fields.Char(string='Atnaujinimo raktas')
    access_token_expires = fields.Datetime(string='Prieigos rato galiojimo data',
                                           help='Prieigos raktai galioja 40 minučių')
    refresh_token_expires = fields.Datetime(string='Atnaujinimo rakto galiojimo data',
                                            help='Atnaujinimo raktai galioja 90 dienų')

    show_create_jwt = fields.Boolean(compute='_compute_show_create_jwt')

    attachment_ids = fields.One2many('ir.attachment', 'res_id', domain=[('res_model', '=', 'revolut.api')],
                                     string='Prisegtukai', groups='base.group_system')

    min_date_from = fields.Datetime(string='Minimali data nuo', help='Neimportuoti transakcijų, senesnių, nei ši data')

    revolut_account_ids = fields.One2many('revolut.account', 'revolut_api_id', string='Sąskaitos')
    accounts_count = fields.Integer(compute='_compute_accounts_count')
    disabled = fields.Boolean(help='Indicates whether this API is enabled and working, or if it should be skipped')

    @api.multi
    def _compute_name(self):
        for rec in self:
            rec.name = 'Revolut API (%s)' % rec.id

    @api.one
    @api.depends('attachment_ids')
    def _compute_x509_public_key(self):
        cert = self.sudo().attachment_ids.filtered(lambda a: a.name == 'cert.pem')
        if cert:
            self.x509_public_key_display = base64.b64decode(cert[0].with_context(bin_size=False).datas)

    @api.one
    @api.depends('attachment_ids')
    def _compute_private_key(self):
        key = self.sudo().attachment_ids.filtered(lambda a: a.name == 'id_rsa')
        if key:
            self.private_key = base64.b64decode(key[0].with_context(bin_size=False).datas)

    @api.one
    @api.depends('attachment_ids')
    def _compute_jwt(self):
        jwt = self.sudo().attachment_ids.filtered(lambda a: a.name == 'jwt')
        if jwt:
            self.jwt = base64.b64decode(jwt[0].with_context(bin_size=False).datas)

    @api.one
    @api.depends('attachment_ids')
    def _compute_show_create_jwt(self):
        jwt = self.sudo().attachment_ids.filtered(lambda a: a.name == 'jwt')
        if not jwt and self.sudo().private_key and self.client_id:
            self.show_create_jwt = True

    @api.one
    def _compute_callback_address(self):
        # self.callback_address = 'https://www.robolabs.lt' #Uncomment on local testing
        # return #Uncomment on local testing
        base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        self.callback_address = '%s/web/revolut/%s' % (base_url, self.id)

    @api.one
    @api.depends('revolut_account_ids')
    def _compute_accounts_count(self):
        self.accounts_count = len(self.revolut_account_ids)

    @api.one
    def _set_client_id(self):
        if self.client_id:
            self.generate_jwt()

    @api.multi
    def name_get(self):
        return [(rec.id, 'Revolut API #%s' % rec.id) for rec in self]

    @api.model
    def create(self, vals):
        res = super(RevolutApi, self).create(vals)
        if not res.x509_public_key_display:
            res.generate_key()
        return res

    @api.multi
    def unlink(self):
        self.mapped('revolut_account_ids').unlink()
        return super(RevolutApi, self).unlink()

    @api.multi
    def generate_key(self):
        """
        Generates a RSA private key and the X509 certificate required by the Revolut Business API.
        Attach them as files linked to the record
        """
        if not self.env.user.has_group('base.group_system'):
            if self.env.user.is_premium_manager():
                return self.sudo().generate_key()
            else:
                raise exceptions.AccessError(_('Šį veiksmą gali atlikti tik vadovas.'))
        self.ensure_one()
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, KEY_SIZE)
        cert = crypto.X509()
        cert.get_subject().C = 'LT'
        cert.get_subject().O = 'RoboLabs'
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(5 * 365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha1')
        self.attachment_ids.filtered(lambda a: a.name in ('id_rsa', 'cert.pem')).unlink()
        self.env['ir.attachment'].sudo().create(
            {
                'res_model': 'revolut.api',
                'name': 'id_rsa',
                'datas_fname': 'id_rsa',
                'res_id': self.id,
                'type': 'binary',
                'datas': base64.b64encode(crypto.dump_privatekey(crypto.FILETYPE_PEM, key)),
            }
        )
        self.env['ir.attachment'].sudo().create(
            {
                'res_model': 'revolut.api',
                'name': 'cert.pem',
                'datas_fname': 'cert.pem',
                'res_id': self.id,
                'type': 'binary',
                'datas': base64.b64encode(crypto.dump_certificate(crypto.FILETYPE_PEM, cert)),
            }
        )
        self.write({'client_id': False}) #Since we lose previous certificate, we should remove client_id
        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def generate_jwt(self):
        """ Generate the JSON encrypted token (issuer is provided by Revolut, corresponds to callback address domain) """
        if not self.env.user.has_group('base.group_system'):
            if self.env.user.is_premium_manager():
                return self.sudo().generate_jwt()
            else:
                raise exceptions.AccessError(_('Šį veiksmą gali atlikti tik vadovas.'))
        self.ensure_one()
        private_key = self.sudo().private_key
        if not private_key:
            return {
            'type': 'ir.actions.do_nothing',
        }
        if not self.client_id:
            raise exceptions.UserError(_('Turite įrašyti kliento ID kad galėtumėte sugeneruoti JWT failą'))
        issuer = self.sudo().env['ir.config_parameter'].get_param('web.base.url').replace('https://', '').replace('http://', '')
        # issuer = 'www.robolabs.lt' #Uncomment on local
        jwt = base64.b64encode(revolut.utils.get_jwt(private_key, issuer, self.client_id))
        self.attachment_ids.filtered(lambda a: a.name in ('jwt',)).unlink()
        self.env['ir.attachment'].sudo().create(
            {
                'res_model': 'revolut.api',
                'name': 'jwt',
                'datas_fname': 'jwt',
                'res_id': self.id,
                'type': 'binary',
                'datas': jwt,
            }
        )
        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def _get_renew_token_url(self):
        """
        Returns the URL for renewing the app authorization
        :rtype: string
        """
        self.ensure_one()
        if self.auth_code and self.auth_code.startswith('oa_sand'):
            url = 'https://sandbox-business.revolut.com/app-confirm'
        else:
            url = 'https://business.revolut.com/app-confirm'
        payload = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.callback_address,
            'scope': 'READ',
        }
        return '{}?{}'.format(url, urlencode(payload))

    @api.multi
    def request_new_app_confirm(self):
        """ Open the authorization page from Revolut API settings """
        self.ensure_one()
        url = self._get_renew_token_url()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url
        }

    @api.multi
    def get_tokens(self):
        """ Get the initial set of tokens """
        self.ensure_one()
        jwt = self.sudo().jwt
        if not self.auth_code:
            raise exceptions.UserError(_('Trūksta OAuth kodo'))
        if not self.client_id:
            raise exceptions.UserError(_('Trūksta kliento ID'))
        if not jwt:
            raise exceptions.UserError(_('Trūksta JWT. Sugeneruokite jį'))
        tp = TokenProvider(self.auth_code, self.client_id, jwt)
        self.access_token_expires = tp.access_token_expires
        self.refresh_token_expires = datetime.now() + relativedelta(days=90)
        self.access_token = tp.access_token
        self.refresh_token = tp.refresh_token
        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def refresh_tokens(self):
        """ Get the currently usable token, refresh it if needed """
        self.ensure_one()
        jwt = self.sudo().jwt
        if not self.refresh_token:
            raise exceptions.UserError(_('Trūksta atnaujinimo rakto, iš pradžių gaukite pradinius raktus'))
        if not self.client_id:
            raise exceptions.UserError(_('Trūksta kliento ID'))
        if not jwt:
            raise exceptions.UserError(_('Trūksta JWT. Sugeneruokite jį'))
        session = RenewableSession(self.refresh_token, self.client_id, jwt)
        self.access_token = session.access_token
        self.access_token_expires = session.access_token_expires
        self.refresh_token = session.refresh_token
        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def _get_authorization_header(self):
        """ Get the Authorization token to make the query. Returns a dict"""
        self.ensure_one()
        if not self.access_token_expires:
            self.refresh_tokens()
        token_expiry = datetime.strptime(self.access_token_expires, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        if token_expiry < datetime.utcnow() + relativedelta(minutes=2):
            self.refresh_tokens()
        return {'Authorization': 'Bearer ' + self.access_token}

    @api.multi
    def _get_url(self):
        """ Get the base API URL """
        self.ensure_one()
        token = self.access_token
        if token.startswith('oa_prod'):
            return 'https://b2b.revolut.com/api/1.0/'
        elif token.startswith('oa_sand'):
            return 'https://sandbox-b2b.revolut.com/api/1.0/'
        else:
            return None

    @api.multi
    def _make_api_call(self, url):
        """
        Make the API call to the given URL and handle response

        :param url: endpoint URL (str)
        :returns: JSON dict
        """
        def create_ticket_for_accountant(text):
            ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
            description = '''
                    <p>Sveiki,</p>
                    <p> {}
                    <br/>
                    Dėl daugiau informacijos kreiptis
                    <a href="https://pagalba.robolabs.lt/lt/integracijos#revolut-integracija" target="_blank">pagalba.robolabs.lt</a></p>
                    <p>Ačiū</p>'''.format(text)
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': False,
                'ticket_record_id': False,
                'name': 'Revolut klaida',
                'description': description,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError('Failed to create revolut ticket for accountant')
            return res

        self.ensure_one()
        headers = self._get_authorization_header()
        response = requests.get(url=url, headers=headers)
        if response.status_code == 204:
            result = {}
        else:
            result = response.json()

        if response.status_code < 200 or response.status_code >= 300:
            message = result.get('message', 'No message supplied')
            detailed_error = 'HTTP {} for {}: {}'.format(response.status_code, url, message)
            _logger.info('Revolut API error: {}'.format(detailed_error))
            main_error = _('Klaida atkuriant duomenis. Susisiekite su sistemos administratoriumi.')
            if message == 'The request should be authorized.':
                create_ticket_for_accountant('Prašome susisiekti su klientu ir paprašyti, kad patikrintų ar jis įtraukė visus 3 mūsų IP adresus į sąrašą.')
                return {}
            elif 'Please upgrade to a paid plan to continue using the Business API' in message and not self.disabled:
                self.write({'disabled': True})
                create_ticket_for_accountant('Verslo API neleidžiamas dabartiniam įmonės planui. Informuokite klientą, jog jis turėtų atsinaujinti planą, jei nori naudotis šia integracija.')
                return {}
            if self.env.user.has_group('base.group_system'):
                main_error += '\n' + detailed_error
            raise exceptions.UserError(main_error)
        return result

    @api.multi
    def get_transaction(self, uuid):
        """
        Request Get transaction/<id> to API

        :param uuid: string, transaction id in the revolut system
        :returns: a dict containing the detailed information about the transaction
        """
        self.ensure_one()
        url = urljoin(self._get_url(), 'transaction/')
        path = '{}/{}'.format(url, uuid)
        return self._make_api_call(path)

    @api.multi
    def _get_transactions(self, data=None):
        """
        Request Get transactions to API

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
        url = urljoin(self._get_url(), 'transactions')
        path = '{}?{}'.format(url, urlencode(data)) if data else url
        return self._make_api_call(path) or []

    @api.multi
    def _fetch_transactions(self, date_from=None, date_to=None, count=0, counterparty=None, transaction_type=None):
        """
        Prepare a request to send to API

        :param date_from: filter on created_at, date string in server format
        :param date_to: filter on created_at, date string in server format
        :param count: maximum number of transactions (max 1000, default if not specified: 100, -1 for unlimited)
        :param counterparty: a counterparty_id
        :param transaction_type: the transaction type, one of atm, card_payment, card_refund, card_chargeback, card_credit,
                                 exchange, transfer, loan, fee, refund, topup, topup_return, tax, tax_refund

        :returns: a RecordSet of revolut.api.transactions
        """
        self.ensure_one()
        payload = {}
        if date_from:
            payload['from'] = self._convert_date_to_revolut(date_from, self.min_date_from)
        if date_to:
            payload['to'] = self._convert_date_to_revolut(date_to, self.min_date_from)
        if count:
            payload['count'] = count if count > 0 else REVOLUT_MAX_TRANSACTIONS_PER_REQUEST
        if counterparty:
            payload['counterparty'] = counterparty
        if transaction_type:
            payload['type'] = type
        count = int(count) if count else REVOLUT_DEFAULT_TRANSACTIONS_PER_REQUEST
        transactions = self._get_transactions(payload)
        last_transactions = transactions
        while (count < 0 or len(transactions) <= count) and last_transactions:
            payload['to'] = transactions[-1]['created_at']
            if count > 0 and count - len(transactions) > payload['count']:
                payload['count'] = min(count - len(transactions), REVOLUT_MAX_TRANSACTIONS_PER_REQUEST)
            last_transactions = self._get_transactions(payload)
            transactions.extend(last_transactions)
        return transactions

    @api.multi
    def get_transactions(self, date_from=None, date_to=None, count=0, counterparty=None, transaction_type=None):
        self.ensure_one()
        transactions = self._fetch_transactions(date_from, date_to, count, counterparty, transaction_type)
        return self._save_transactions(transactions)

    @api.multi
    def get_account(self, uuid):
        """
        Request Get account/<id> to API

        :param uuid: string, account id in the revolut system
        :returns: a dict containing the detailed information about the account
        """
        self.ensure_one()
        url = urljoin(self._get_url(), 'accounts')
        path = '{}/{}'.format(url, uuid)
        return self._make_api_call(path)

    @api.multi
    def _get_accounts(self):
        """
        Request Get accounts to API

        :returns: a list of account values in dicts
        """
        self.ensure_one()
        url = urljoin(self._get_url(), 'accounts')
        return self._make_api_call(url) or []

    @api.multi
    def get_accounts(self):
        """
        Make request to API to retrieve Account info and create matching revolut.account records if needed
        """
        self.ensure_one()
        RevolutAccount = self.env['revolut.account']
        accounts = self.env['revolut.account']
        data = self._get_accounts()
        for account_data in data:
            account = RevolutAccount.search([('uuid', '=', account_data.get('id'))], limit=1)
            if not account:
                if RevolutAccount.search([('uuid', '=', False),
                                          ('revolut_api_id', '=', self.id),
                                          ('name', '=', account_data.get('name'))], limit=1):
                    raise exceptions.UserError(
                        _('Sąskaita su šiuo pavadinimu %s jau egzistuoja') % account_data.get('name'))
                currency = account_data.get('currency')
                if not currency:
                    raise exceptions.UserError(_('Nerasta valiuta, sąskaita %s') % account_data.get('name'))
                currency_id = self.env['res.currency'].search([('name', '=', currency)])
                is_currency_crypto = currency in CRYPTO_CURRENCIES.keys()
                if not currency_id:
                    if is_currency_crypto:
                        _logger.info('Account {0} will use crypto-currency {1} ({2}) as currency'.format(
                            account_data.get('name'), currency, CRYPTO_CURRENCIES[currency]))
                    else:
                        raise exceptions.UserError(_('Nerasta valiuta %s') % currency)
                name = account_data.get('name') or ''
                if is_currency_crypto:
                    name = '%s (%s)' % (name, currency)
                try:
                    api = self.revolut_api_id
                    response = api.get_bank_account_details_response(account_data.get('id'))
                    bank_account_iban, bank_account_bic = api.get_bank_account_details(response)
                except Exception:
                    bank_account_iban = False
                    bank_account_bic = False
                account = RevolutAccount.create({
                    'name': name,
                    'uuid': account_data.get('id'),
                    'currency_id': currency_id.id if not is_currency_crypto else False,
                    'is_currency_crypto': is_currency_crypto,
                    'revolut_api_id': self.id,
                    'bank_account_iban': bank_account_iban,
                    'bank_account_bic': bank_account_bic,
                })
                accounts |= account
        return accounts

    @api.multi
    def get_bank_account_details_response(self, uuid):
        self.ensure_one()
        url = self._get_url().strip('/') + '/accounts'
        path = '{}/{}/{}'.format(url.strip('/'), uuid, 'bank-details')
        return self._make_api_call(path) or []

    @api.model
    def get_bank_account_details(self, bank_account_details_response):
        iban, bic = '', ''
        for scheme in bank_account_details_response:
            if 'sepa' in scheme.get('schemes') or 'swift' in scheme.get('schemes'):
                iban = scheme.get('iban')
                bic = scheme.get('bic')
                if 'sepa' in scheme.get('schemes'):
                    break
        return iban, bic

    @api.multi
    def _process_leg_data(self, legs):
        """
        Process leg data
        :param legs:
        :return: True if processed, False if not
        """
        self.ensure_one()
        RevolutAccount = self.env['revolut.account']
        for leg in legs:
            account = RevolutAccount.search([('uuid', '=', leg.get('account_id'))], limit=1)
            if not account:
                try:
                    account_data = self.get_account(leg.get('account_id'))
                except:
                    _logger.info('Revolut API: account %s for transaction leg %s was not found. Setting to False.',
                                 leg.get('account_id'), leg.get('leg_id'))
                    leg.update(revolut_account_id=None)
                    continue
                currency = account_data.get('currency')
                if not currency:
                    raise exceptions.UserError(_('Nerasta valiuta, sąskaita %s') % account_data.get('name'))
                currency_id = self.env['res.currency'].search([('name', '=', currency)])
                is_currency_crypto = currency in CRYPTO_CURRENCIES.keys()
                if not currency_id:
                    if is_currency_crypto:
                        _logger.info('Account {0} will use crypto-currency {1} ({2}) as currency'.format(
                            account_data.get('name'), currency, CRYPTO_CURRENCIES[currency]))
                    else:
                        raise exceptions.UserError(_('Nerasta valiuta %s') % currency)
                account = RevolutAccount.with_context(skip_journal_creation=True).create({
                    'name': account_data.get('name'),
                    'uuid': leg.get('account_id'),
                    'currency_id': currency_id.id if not is_currency_crypto else False,
                    'is_currency_crypto': is_currency_crypto,
                    'revolut_api_id': self.id,
                })
            leg.update(revolut_account_id=account.id)

        return True

    @api.multi
    def _save_transactions(self, data):
        """
        Save the provided API data to revolut.api.transaction records
        :param data: a list of dict containing transaction values, as provided by _get_transactions method
        :returns: a revolut.api.transaction RecordSet containing the newly created or updated transaction records
        """
        self.ensure_one()
        RevolutApiTransaction = self.env['revolut.api.transaction']
        journal = self._context.get('importing_to_journal')
        transactions = self.env['revolut.api.transaction']
        for transaction in data:
            uuid = transaction.get('id')
            if not uuid:
                continue
            # search existing one:
            existing_transaction = RevolutApiTransaction.search([('uuid', '=', uuid)], limit=1)
            if existing_transaction:
                existing_transaction._update_transaction_values(transaction)
                transactions |= existing_transaction
                continue
            legs = transaction.get('legs')
            if not self._process_leg_data(legs):
                continue
            if journal and all(leg['revolut_account_id'] != journal.revolut_account_id.id for leg in legs):
                continue
            vals = RevolutApiTransaction.get_creation_values(transaction)
            vals.update(revolut_api_id=self.id)
            transactions |= RevolutApiTransaction.create(vals)
        return transactions

    @api.model
    def cron_send_authorization_reminders(self):
        date_lim = (datetime.today() + relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        revolut_apis = self.env['revolut.api'].search([
            ('client_id', '!=', False),
            ('refresh_token_expires', '!=', False),
            ('refresh_token_expires', '<=', date_lim),
        ])
        for rev_api in revolut_apis:
            url = rev_api._get_renew_token_url()
            #TODO: send nice email with button

    @staticmethod
    def _convert_date_to_revolut(date, min_date=None):
        """
        Converts system date to Revolut ISO format timestamps for API requests
        """
        try:
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        except:
            date_dt = date
        if min_date:
            min_date_dt = datetime.strptime(min_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date_dt = max(date_dt, min_date_dt)
        return date_dt.strftime(REVOLUT_DATETIME_FORMAT)
