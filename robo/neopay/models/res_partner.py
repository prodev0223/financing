# -*- coding: utf-8 -*-

import urllib
from datetime import datetime

import jwt
from dateutil.relativedelta import relativedelta

from odoo import api, models, tools
from .res_company import JWTEncryptionAlgorithm, ROBO_CLIENT_SECRET, URL_BASE


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.multi
    def _get_apr_email_context_from_settings(self, settings):
        self.ensure_one()
        res = super(ResPartner, self)._get_apr_email_context_from_settings(settings)
        company = self.company_id or self.env.user.company_id or self.env['res.company'].search([], limit=1)
        currencies = settings.get('currencies')
        single_currency_debt = currencies and len(currencies) == 1
        show_pay_now_link = company.enable_neopay_integration and company.has_lithuanian_iban and \
                            company.company_registry and single_currency_debt
        res['show_pay_now_link'] = False
        res['pay_now_link'] = None
        if show_pay_now_link:
            total_unpaid_amount = settings.get('total_amount_left_unpaid', 0.0)
            if tools.float_compare(total_unpaid_amount, 0.0, precision_digits=2) > 0:
                res['show_pay_now_link'] = True
                data = {
                    'company_code': company.company_registry,
                    'amount': total_unpaid_amount,
                    'currency': currencies.name,
                    'exp': datetime.utcnow() + relativedelta(years=1)
                }
                encoded_data_token = jwt.encode(data, ROBO_CLIENT_SECRET, algorithm=JWTEncryptionAlgorithm)
                res['pay_now_link'] = '{}/paydebt/{}'.format(URL_BASE, urllib.quote(encoded_data_token))
        return res

    @api.model
    def _get_apr_template_dict(self):
        templates = super(ResPartner, self)._get_apr_template_dict()
        templates.update({
            'before': 'neopay.apr_email_template_res_partner_before_invoice',
            'today': 'neopay.apr_email_template_res_partner_on_date_invoice',
            'after': 'neopay.apr_email_template_res_partner_after_invoice'
        })
        return templates


ResPartner()
