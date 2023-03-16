# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, models, fields

from dateutil.relativedelta import relativedelta

import jwt
import urllib

from .res_company import JWTEncryptionAlgorithm, URL_BASE, ROBO_CLIENT_SECRET


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    neopay_pay_now_url = fields.Char(compute='_compute_neopay_pay_now_url')

    @api.multi
    def _compute_show_payment_url(self):
        for rec in self:
            company = rec.company_id
            states_to_show_in = ['open', 'proforma', 'proforma2']
            force_show = self._context.get('force_show_in_paid')
            if force_show:
                states_to_show_in.append('paid')
            show_payment_url = company.enable_neopay_integration and \
                               rec.state in states_to_show_in and \
                               rec.type in ['out_invoice'] and \
                               company.company_registry and \
                               company.has_lithuanian_iban
            if not force_show:
                show_payment_url = show_payment_url and not rec.paid_using_online_payment_collection_system
            rec.show_payment_url = show_payment_url

    @api.multi
    def _compute_invoice_payment_url(self):
        for rec in self:
            rec.invoice_payment_url = rec.neopay_pay_now_url

    @api.multi
    def _compute_neopay_pay_now_url(self):
        company_code = self.env.user.sudo().company_id.company_registry
        for rec in self:
            data = {
                'company_code': company_code,
                'invoice_id': rec.id,
                'exp': datetime.utcnow()+relativedelta(years=1)
            }
            encoded_data_token = jwt.encode(data, ROBO_CLIENT_SECRET, algorithm=JWTEncryptionAlgorithm)
            rec.neopay_pay_now_url = '{}/pay/{}'.format(URL_BASE, urllib.quote(encoded_data_token))

    @api.multi
    def _get_invoice_data_for_neopay(self):
        """
        Called from internal by Neopay.
        Returns: (dict) invoice data

        """
        self.ensure_one()

        company = self.company_id

        if not self.with_context(force_show_in_paid=True).show_payment_url:
            return

        payment_data = company._get_company_data_for_neopay_transaction()

        # Generate a transaction id
        epoch = datetime.utcfromtimestamp(0)
        seconds_since_epoch = int((datetime.utcnow() - epoch).total_seconds())
        # Transaction ID must be unique for each payment initiation
        transaction_id = 'C{}I{}T{}'.format(company.company_registry, self.id, seconds_since_epoch)

        payment_purpose = self.computed_number or self.reference
        state = 'paid' if self.paid_using_online_payment_collection_system else self.state

        payment_data.update({
            "amount": 0.0 if state == 'paid' else max(self.residual_signed, 0.0),
            "paymentPurpose": payment_purpose,
            "transactionId": transaction_id,
            "currency": self.currency_id.name,
            "invoiceState": state,
            "invoice_id": self.id,
        })
        return payment_data


AccountInvoice()
