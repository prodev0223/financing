# -*- encoding: utf-8 -*-
import time
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools
from six import itervalues


_logger = logging.getLogger(__name__)


REVOLUT_ACCESS_REQUEST_LIMIT = 60
REVOLUT_IMPORT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'


class RevolutApiTransaction(models.Model):
    _name = 'revolut.api.transaction'
    _description = 'Store transaction info from Revolut Business API'

    revolut_api_id = fields.Many2one('revolut.api', required=True)
    uuid = fields.Char(string='ID (Revolut)', required=True)
    created_at = fields.Datetime(string='Sukurta')
    updated_at = fields.Datetime(string='Atnaujinta')
    completed_at = fields.Datetime(string='Užbaigta')
    merchant_name = fields.Char()
    reference = fields.Char()
    request_id = fields.Char()
    related_transaction_uiid = fields.Char(string='Related transaction ID')
    reason_code = fields.Char()
    transaction_type = fields.Selection([
        ('atm', 'ATM'),
        ('card_payment', 'Card payment'),
        ('card_refund', 'Card refund'),
        ('card_chargeback', 'Card chargeback'),
        ('card_credit', 'Card credit'),
        ('exchange', 'Exchange'),
        ('transfer', 'Transfer'),
        ('loan', 'Loan'),
        ('fee', 'Fee'),
        ('refund', 'Refund'),
        ('reward', 'Reward'),
        ('topup', 'Top-up'),
        ('topup_return', 'Top-up return'),
        ('tax', 'Tax'),
        ('tax_refund', 'Tax refund')], string='Type', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('declined', 'Declined'),
        ('failed', 'Failed'),
        ('reverted', 'Reverted')
    ])
    leg_ids = fields.One2many('revolut.api.transaction.leg', 'transaction_id')
    completed_day = fields.Date(compute='_compute_completed_date')
    bank_statement_line_ids = fields.Many2many('account.bank.statement.line', string='Banko išrašo eilutės',
                                               compute='_compute_bank_statement_line_ids')

    _sql_constraints = [('uniq_uuid', 'unique(uuid)', 'Transakcijos ID turi būti unikalus')]
    _order = 'completed_at, created_at'

    @api.one
    @api.depends('completed_at')
    def _compute_completed_date(self):
        if self.completed_at:
            self.completed_day = datetime.strptime(self.completed_at, tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT
            )

    @api.one
    def _compute_bank_statement_line_ids(self):
        lines = self.env['account.bank.statement.line'].search([
            '|', ('entry_reference', '=', self.uuid),
            ('commission_of_id.entry_reference', '=', self.uuid),
            ('journal_id.revolut_account_id.revolut_api_id', '=', self.revolut_api_id.id)
        ])
        self.bank_statement_line_ids = [(6, 0, lines.ids)]

    @api.multi
    def name_get(self):
        return [(rec.id, rec.uuid) for rec in self]

    @api.multi
    def unlink(self):
        if self.mapped('bank_statement_line_ids'):
            raise exceptions.UserError(_('Transakcijos turi susijusias banko išrašų eilutes, trinti negalima'))
        return super(RevolutApiTransaction, self).unlink()

    @api.model
    def get_creation_values(self, data):
        """ Return the dict of values for call to create, from the data returned by the API """
        leg_vals = [{
            'description': leg.get('description'),
            'uuid': leg.get('leg_id'),
            'account_uuid': leg.get('account_id'),
            'amount': float(leg.get('amount', 0)),
            'fee': float(leg.get('fee', 0)),
            'balance': float(leg.get('balance', 0)),
            'currency': leg.get('currency'),
            'bill_currency': leg.get('bill_currency'),
            'bill_amount': float(leg.get('bill_amount')) if leg.get('bill_amount') else False,
        } for leg in data.get('legs', [])]

        vals = {
            'revolut_api_id': self.id,
            'merchant_name': data.get('merchant', {}).get('name'),
            'uuid': data.get('id'),
            'created_at': data.get('created_at'),
            'completed_at': data.get('completed_at'),
            'updated_at': data.get('updated_at'),
            'transaction_type': data.get('type'),
            'reason_code': data.get('reason_code'),
            'reference': data.get('reference'),
            'state': data.get('state'),
            'request_id': data.get('request_id'),
            'leg_ids': [(0, 0, leg) for leg in leg_vals]
        }
        return vals

    @api.multi
    def _update_transaction_values(self, data):
        """ Update transaction with data dictionary provided by the API """
        self.ensure_one()
        if data.get('id') != self.uuid:
            raise exceptions.UserError(_('Jūs bandote atnaujinti transakcija su duomenimis iš kitos transakcijos!'))
        leg_data = {
            leg.get('leg_id'): {
                'description': leg.get('description'),
                'uuid': leg.get('leg_id'),
                'account_uuid': leg.get('account_id'),
                'amount': float(leg.get('amount', 0)),
                'fee': float(leg.get('fee', 0)),
                'balance': float(leg.get('balance', 0)),
                'currency': leg.get('currency'),
                'bill_currency': leg.get('bill_currency'),
                'bill_amount': float(leg.get('bill_amount')) if leg.get('bill_amount') else False, }
            for leg in data.get('legs', [])}
        leg_ids = []
        # Assume legs could have changed, so we update existing, delete missing and create new ones
        for leg in self.leg_ids:
            leg_vals = leg_data.pop(leg.uuid, 0)
            if leg_vals:
                leg_ids.append((1, leg.id, {k: leg_vals[k] for k in ['amount', 'fee', 'balance', 'bill_amount']}))
            else:
                leg_ids.append((2, leg.id, 0))
        leg_ids.extend((0, 0, vals) for vals in itervalues(leg_data))
        self.write({
            'updated_at': data.get('updated_at', self.updated_at),
            'completed_at': data.get('completed_at'),
            'state': data.get('state'),
            'leg_ids': leg_ids,
        })

    @api.multi
    def _fetch_transaction_data(self):
        self.ensure_one()
        return self.revolut_api_id.get_transaction(self.uuid)

    @api.multi
    def check_for_updates(self):
        """ Query new data from the API to update transactions """
        for transaction in self:
            data = transaction._fetch_transaction_data()
            if self.env.context.get('revolut_api_sleep_between_queries'):
                time.sleep(1)
            if not data:  # If query fails, it might return empty data (d6b793ca)
                _logger.info('Skipping transaction update for transaction %s. No data fetched.', transaction.uuid)
                continue
            transaction._update_transaction_values(data)

    @api.multi
    def _update_transaction(self):
        if any(t.state != 'pending' for t in self):
            raise exceptions.UserError(_('Only transactions in state "pending" can be updated'))
        self.check_for_updates()
        self.filtered(lambda t: t.state == 'completed').mapped('leg_ids').create_statements(apply_import_rules=True)

    @api.multi
    def btn_update_transaction(self):
        self.ensure_one()
        self._update_transaction()

    @api.model
    def cron_update_pending_transactions(self):
        """ Check transactions in pending state and update their status if needed """
        # We assume that transactions older than a month will not change status anymore
        # but there are no explicit restrictions in the API about it
        # Older transactions can be checked manually
        date_lim = (datetime.now() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        transactions = self.env['revolut.api.transaction'].search([('state', '=', 'pending'),
                                                                   ('revolut_api_id.disabled', '!=', True),
                                                                   ('created_at', '>', date_lim)], order='created_at',
                                                                  limit=3*REVOLUT_ACCESS_REQUEST_LIMIT)
        for transaction in transactions:
            transaction.check_for_updates()
            if transaction.state == 'completed':
                transaction.mapped('leg_ids').create_statements(apply_import_rules=True)
                self.env.cr.commit()
            time.sleep(1)  # ensure we don't go over 60 requests per minutes to API
