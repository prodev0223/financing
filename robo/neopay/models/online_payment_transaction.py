# -*- coding: utf-8 -*-
from datetime import datetime

import pytz

from odoo import _, api, fields, models, tools
from six import iteritems


class OnlinePaymentTransaction(models.Model):
    _name = 'online.payment.transaction'

    transaction_key = fields.Char(string='Transaction key', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    payment_purpose = fields.Char(string='Payment purpose')
    payer_account_number = fields.Char(string='Payer account number')
    receiver_name = fields.Char(string='Receiver')
    receiver_account_number = fields.Char('Receiver account number')
    partner_id = fields.Many2one('res.partner', string='Partner who paid', compute='_compute_partner_id', store=True)
    invoice_id = fields.Many2one('account.invoice', compute='_compute_invoice_id', store=True,
                                 inverse='_update_invoice_paid_using_online_payment_collection_system')

    @api.multi
    @api.depends('payer_account_number')
    def _compute_partner_id(self):
        for rec in self:
            partner = None
            if rec.payer_account_number:
                bank = self.env['res.partner.bank'].sudo().search([('acc_number', '=', rec.payer_account_number)])
                if bank:
                    partner = bank.partner_id
            if not partner and rec.invoice_id:
                partner = rec.invoice_id.partner_id
            rec.partner_id = partner.id if partner else None

    @api.multi
    @api.depends('transaction_key')
    def _compute_invoice_id(self):
        for rec in self:
            transaction_key = rec.transaction_key
            invoice_id = self._get_invoice_id_from_transaction_key(transaction_key)
            invoice = None
            if invoice_id:
                invoice = self.env['account.invoice'].browse(invoice_id)
            rec.invoice_id = invoice.id if invoice else False

    @api.model
    def _get_invoice_id_from_transaction_key(self, transaction_key):
        try:
            return int(transaction_key.split('I')[1].split('T')[0])
        except:
            return

    @api.multi
    def _update_invoice_paid_using_online_payment_collection_system(self):
        invoices_set_as_paid_using_online_payment_collection_system = self.env['account.invoice'].search([
            ('paid_using_online_payment_collection_system', '=', True)
        ])
        invoices_actually_paid_using_online_payment_collection_system = self.search([
            ('invoice_id', '!=', False)
        ]).mapped('invoice_id').filtered(lambda invoice: invoice.type in ['out_invoice', 'out_refund'])

        invoices_actually_paid_using_online_payment_collection_system.write({
            'paid_using_online_payment_collection_system': True
        })
        invoices_set_as_paid_using_online_payment_collection_system.filtered(
            lambda invoice: invoice.id not in invoices_actually_paid_using_online_payment_collection_system.ids
        ).write({
            'paid_using_online_payment_collection_system': False
        })

    @api.model
    def _create_payment_transactions_from_neopay_transactions(self, transactions, notify_partners_upon_creation=True):
        def _get_currency_id_from_name(currency_name):
            currency_eur = self.env['res.currency'].search([('name', '=', 'EUR')], limit=1)
            currency = self.env['res.currency'].search([('name', '=ilike', currency_name)], limit=1)
            return currency.id if currency else currency_eur.id

        neopay_transaction_field_mapping = {
            'currency': 'currency_id',
            'paymentPurpose': 'payment_purpose',
            'payerAccountNumber': 'payer_account_number',
            'receiverName': 'receiver_name',
            'receiverAccountNumber': 'receiver_account_number',
        }
        neopay_transaction_value_process_methods = {
            'currency': _get_currency_id_from_name
        }
        payment_transactions = self
        transaction_keys = transactions.keys()
        existing_transactions = self.sudo().search([('transaction_key', 'in', transaction_keys)])
        existing_keys = existing_transactions.mapped('transaction_key')
        for transaction_key, transaction_data in iteritems(transactions):
            values = {'transaction_key': transaction_key}
            for transaction_attr, attr_value in iteritems(transaction_data):
                field_name = neopay_transaction_field_mapping.get(transaction_attr) or transaction_attr
                if field_name not in self._fields:
                    continue
                field_value = attr_value
                value_process_method = neopay_transaction_value_process_methods.get(transaction_attr)
                if value_process_method:
                    field_value = value_process_method(field_value)
                values[field_name] = field_value
            newly_created_transaction = self.env['online.payment.transaction'].create(values)
            if transaction_key in existing_keys:
                # Create the transaction but don't notify partners about those transactions since they already exist
                continue
            payment_transactions |= newly_created_transaction

        if notify_partners_upon_creation:
            payment_transactions._notify_partner_about_received_transaction()

    @api.multi
    def _notify_partner_about_received_transaction(self):
        for transaction in self:
            partner = transaction.partner_id
            if not partner:
                continue
            email = partner.email
            if not email:
                continue
            now = datetime.utcnow()
            tz_name = self.env.context.get('tz') or self.env.user.tz or 'Europe/Vilnius'
            if tz_name:
                user_tz = pytz.timezone(tz_name)
                now = pytz.utc.localize(now).astimezone(user_tz)
            now = now.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

            company = transaction.invoice_id.company_id if transaction.invoice_id else self.env.user.company_id

            subject = _('Mokėjimas atliktas')
            message = _('''
                <div style="font-family:arial,helvetica neue,helvetica,sans-serif">
                    Sveiki,<br/>
                    pardavėjui <span style="font-weight: bold;">{0}</span>
                    Jūs sumokėjote <span style="font-weight: bold;">{1} {2}</span>
                    <br/>
                    <br/>
                    <table style="font-size: 14px; width: 100%;">
                        <tr>
                            <td style="font-weight: bold;">Data</td>
                            <td style="text-align: right;">{3}</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold;">Unikalus mokėjimo numeris</td>
                            <td style="text-align: right;">{4}</td>
                        </tr>
                    </table>
                    <br/>Pardavėjas<br/>
                    <div style="border-width: 2px; border-style: solid; border-color: #337ab7; color:black; padding: 10px;">
                        <table style="font-size: 14px !important; color: black; width: 100%;">
                            <tr >
                                <td style="line-height: 30px;">{0}</td>
                                <td style="text-align: right; line-height: 30px;">{5}</td>
                            </tr>
                            <tr>
                                <td style="line-height: 30px;">{6}</td>
                                <td style="text-align: right; line-height: 30px;">{7}</td>
                            </tr>
                            <tr>
                                <td style="line-height: 30px;" colspan="2">{8}</td>
                            </tr>
                        </table>
                    </div>
                    <br/>
                    <div style="font-size: 13px; color: gray;">
                        Prašome išsaugoti šį laišką, nes tai yra atlikto mokėjimo įrodymas.
                    </div>
                </div>
                ''').format(
                company.name,
                transaction.amount,
                transaction.currency_id.name,
                now,
                transaction.transaction_key,
                '''<a href="mailto:{0}" style="color:black;">{0}</a>'''.format(company.email) if company.email else '',
                '''<a href="{0}" style="color:black;">{0}</a>'''.format(company.website) if company.website else '',
                company.phone or '',
                (company.street + ', ' if company.street else '') +
                (company.street2 + ', ' if company.street2 else '') +
                (company.city or ''),
            )
            self.env['script'].send_email(emails_to=[email], subject=subject, body=message)

    @api.model
    def create(self, vals):
        recs = super(OnlinePaymentTransaction, self).create(vals)
        recs._update_invoice_paid_using_online_payment_collection_system()
        return recs


OnlinePaymentTransaction()
