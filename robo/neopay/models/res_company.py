# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import fields, models, api, tools

JWTEncryptionAlgorithm = 'HS256'
URL_BASE = 'https://www.robolabs.lt'
ROBO_CLIENT_SECRET = 'cWghAoFzApwzHQsuokQbLJ22CLgM8V1'


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_neopay_integration = fields.Boolean(string='Enable Neopay integration', default=False)
    has_lithuanian_iban = fields.Boolean(compute='_compute_has_lithuanian_iban')

    @api.multi
    def _compute_has_lithuanian_iban(self):
        for rec in self:
            bank_accounts = self.env['account.journal'].sudo().search([
                ('type', '=', 'bank'),
                ('company_id', '=', rec.id)
            ])
            rec.has_lithuanian_iban = any(bank_account.bank_acc_number and bank_account.bank_acc_number.startswith('LT')
                                          for bank_account in bank_accounts)

    @api.multi
    def _get_company_data_for_neopay_transaction(self, preferred_currency=None):
        self.ensure_one()

        # Determine the bank account number
        bank_accounts = self.env['account.journal'].search([
            ('type', '=', 'bank')
        ]).filtered(lambda acc: acc.bank_acc_number and acc.bank_acc_number.startswith('LT'))
        eur_currency = self.env['res.currency'].search([
            ('name', '=', 'EUR')
        ], limit=1)
        accepted_currencies = list()
        if preferred_currency:
            accepted_currencies.append(preferred_currency.id)
        if preferred_currency == eur_currency:
            # Some banks with EUR currency might not have currency set
            accepted_currencies.append(False)
        bank_accounts_for_currency = bank_accounts.filtered(lambda acc: acc.currency_id.id in accepted_currencies)
        if bank_accounts_for_currency:
            bank_accounts = bank_accounts_for_currency
        shown_on_footer_accounts = bank_accounts.filtered(lambda acc: acc.display_on_footer)
        if shown_on_footer_accounts:
            bank_accounts = shown_on_footer_accounts
        bank_account = bank_accounts and bank_accounts[0]
        bank_account_number = bank_account.bank_acc_number if bank_account else False

        return {
            "receiverName": self.name,
            "receiverAccountNumber": bank_account_number,
        }

    @api.multi
    def _get_neopay_data_for_debt_transaction(self, amount, currency_name):
        self.ensure_one()

        currency = self.env['res.currency'].search([
            ('name', '=', currency_name)
        ], limit=1)

        if not self.enable_neopay_integration or not self.has_lithuanian_iban or \
                tools.float_compare(amount, 0.0, precision_digits=2) < 0 or not currency:
            return dict()

        payment_data = self._get_company_data_for_neopay_transaction(currency)

        # Generate a transaction id
        epoch = datetime.utcfromtimestamp(0)
        seconds_since_epoch = int((datetime.utcnow() - epoch).total_seconds())
        # Transaction ID must be unique for each payment initiation
        transaction_id = 'C{}E{}V{}T{}'.format(
            self.company_registry,
            str(amount).replace('.', 'D'),
            currency.name,
            seconds_since_epoch
        )

        payment_purpose = 'Skolos grąžinimas'

        payment_data.update({
            "amount": amount,
            "paymentPurpose": payment_purpose,
            "transactionId": transaction_id,
            "currency": currency.name,
        })
        return payment_data


ResCompany()
