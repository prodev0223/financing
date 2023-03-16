# -*- encoding: utf-8 -*-
import paypalrestsdk
import werkzeug
import logging
from paypalrestsdk import exceptions as PayPalException
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools

_logger = logging.getLogger(__name__)

PAYPAL_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S+0000'


class PaypalApi(models.Model):
    _name = 'paypal.api'
    _description = 'Table to store Paypal accounts settings'

    name = fields.Char(string='Pavadinimas', compute='_compute_name')
    client_id = fields.Char(string='Paypal kliento ID', readonly=False)
    secret = fields.Char(string='Paypal slaptas raktažodis', readonly=False)
    sandbox = fields.Boolean(string='Paypal testinė aplinka', readonly=False, default=False)
    journal_ids = fields.One2many('account.journal', 'paypal_api_id', string='Žurnalai')
    cron_fetch = fields.Boolean(string='Suplanuotas automatinis pasileidimas', readonly=False, default=False)

    @api.multi
    def _compute_name(self):
        for rec in self:
            rec.name = 'Paypal API (%s)' % rec.client_id

    @api.model
    def create(self, vals):
        res = super(PaypalApi, self).create(vals)
        paypal_journals = self.env['account.journal'].sudo().search([('type', '=', 'bank'), ('import_file_type', '=', 'paypal')])
        if paypal_journals:
            paypal_journals.write({'paypal_api_id': res.id})
        if not res.journal_ids and not self.env.context.get('skip_journal_creation'):
            name = res.client_id and res.client_id.ljust(3, '-')[0:3]
            journal_vals = {
                'type': 'bank',
                'name': 'Paypal (%s)' % name,
                'code': 'PP' + name,
                'import_file_type': 'paypal',
                'paypal_api_id': res.id,
            }
            self.env['account.journal'].sudo().create(journal_vals)
        return res

    @api.multi
    def check_credentials_validity(self):
        """ Make a dummy request to check if credentials are alright """
        self.ensure_one()
        if not self.client_id:
            raise exceptions.ValidationError(_('Client ID is not set'))
        if not self.secret:
            raise exceptions.ValidationError(_('API secret is not set'))
        date_to = datetime.utcnow()
        date_from = date_to + relativedelta(days=-15)
        try:
            api_client = paypalrestsdk.Api({
                'mode': 'sandbox' if self.sandbox else 'live',
                'client_id': self.client_id,
                'client_secret': self.secret,
            })
            fragment = {
                'start_date': date_from.strftime(PAYPAL_DATETIME_FORMAT),
                'end_date': date_to.strftime(PAYPAL_DATETIME_FORMAT),
                'fields': 'all',
                'transaction_status': 'S', #TODO: should get also reversed / denied?
                'balance_affecting_records_only': 'Y',
                'page_size': 1,
            }
            request_url = 'v1/reporting/transactions?' + werkzeug.url_encode(fragment)
            transactions_response = api_client.get(request_url)
            if 'error' in transactions_response.keys():
                raise exceptions.UserError(transactions_response['error']['message'])
        except PayPalException.UnauthorizedAccess:
            raise exceptions.UserError(_(u'Netinkami prieigos raktai. Pakeisikte juos PayPal nustatymuose'))
        except PayPalException.ForbiddenAccess:
            raise exceptions.UserError(
                _(u'Neturite teisių importuoti tranzakcijas iš PayPal. Pakeisikte nustatymus PayPal platformoje'))
        except Exception as e:
            _logger.info('Failed Paypal API request: Error: %s', e)
            raise exceptions.UserError(_(u'Įvyko nenumatyta klaida importuojant tranzakcijas iš PayPal'))

        raise exceptions.UserError(_('Integration with Paypal is successful'))

    @api.model
    def api_fetch_account_balance(self, journal, date_at=None):
        """
        Fetches end balance for specific Paypal journal based on the date
        :param journal: account.journal (record)
        :param date_at: Balance at date (datetime object)
        :return: API balance data (dict)
        """
        # Prepare base parameters
        date_at_dt = date_at or datetime.utcnow()
        currency_code = journal.currency_id.name or self.env.user.company_id.currency_id.name
        try:
            # Prepare API connection
            api_client = paypalrestsdk.Api({
                'mode': 'sandbox' if journal.paypal_api_id.sandbox else 'live',
                'client_id': journal.paypal_api_id.client_id,
                'client_secret': journal.paypal_api_id.secret
            })
            # Format the query and call the endpoint
            query_parameters = {
                'start_date': date_at_dt.strftime(PAYPAL_DATETIME_FORMAT),
                'currency_code': currency_code,
            }
            request_url = 'v1/reporting/balances?' + werkzeug.url_encode(query_parameters)
            balance_response = api_client.get(request_url)
        except Exception as exc:
            # Do not raise here, since this action is always executed in the background
            _logger.info('Failed Paypal API balance request: Error: %s', tools.ustr(exc))
            balance_response = {}
        return balance_response

    @api.model
    def cron_fetch_account_balances(self):
        """
        Fetches end balances for every configured Paypal journal
        :return: None
        """
        # Get the journals, later filtering is applied on compute field
        paypal_journals = self.env['account.journal'].search([
            ('import_file_type', '=', 'paypal'),
        ]).filtered(lambda x: x.has_api_import)
        for journal in paypal_journals:
            balance_data = self.api_fetch_account_balance(journal)
            if balance_data:
                try:
                    # If we fail to parse any part of the value, we just skip without updating
                    balance_amount = float(balance_data['balances'][0]['available_balance']['value'])
                    update_date = parse(balance_data['as_of_time']).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                except Exception as exc:
                    _logger.info('CRON: Paypal API: Failed to extract balance value: Error: %s', tools.ustr(exc))
                else:
                    # Write the balance and normalize statements
                    journal.write({
                        'api_end_balance': balance_amount,
                        'api_balance_update_date': update_date,
                    })

    @api.multi
    def create_new_wizard(self, date_from, date_to):
        """Creating new wizard for cron"""
        paypal_journals = self.env['account.journal'].search([
            ('import_file_type', '=', 'paypal'),
            ('paypal_api_id.cron_fetch', '=', True),
        ]).filtered(lambda x: x.has_api_import)
        for journal in paypal_journals:
            # Create am import wizard
            import_wizard = self.env['paypal.api.import'].create({
                'journal_id': journal.id,
                'date_from': date_from,
                'date_to': date_to,
            })
            import_wizard.query_statements_via_api(raise_if_no_transaction=False)

    @api.model
    def cron_fetch_statements_daily(self):
        """
        Cron that fetches daily bank statements for PayPal accounts
        :return: None
        """
        date_from = (datetime.utcnow() + relativedelta(days=-1, hour=0, minute=0, second=0)).strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to = (datetime.utcnow() + relativedelta(days=-1, hour=23, minute=59, second=59)).strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.create_new_wizard(date_from, date_to)

    @api.model
    def cron_fetch_statements_weekly(self):
        """
        Cron that fetches weekly bank statements for PayPal accounts
        :return: None
        """
        date_from = (datetime.utcnow() + relativedelta(days=-7, hour=0, minute=0, second=0)).strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_to = (datetime.utcnow() + relativedelta(days=-1, hour=23, minute=59, second=59)).strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.create_new_wizard(date_from, date_to)
