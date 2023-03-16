# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from datetime import datetime
import time


class res_company(models.Model):
    """override company to add currency update"""

    _inherit = "res.company"

    # Activate the currency update
    auto_currency_up = fields.Boolean(
        string='Automatic Update',
        help="Automatic update of the currencies for this company")
    # Function field that allows to know the
    # multi company currency implementation
    multi_company_currency_enable = fields.Boolean(
        string='Multi company currency', translate=True,
        compute="_compute_multi_curr_enable",
        help="When this option is unchecked it will allow users "
             "to set a distinct currency updates on each company."
        )
    # List of services to fetch rates
    services_to_use = fields.One2many(
        'currency.rate.update.service',
        'company_id',
        string='Currency update services')

    @api.multi
    def _compute_multi_curr_enable(self):
        "check if multi company currency is enabled"
        company_currency = self.env['res.currency'].search_count([])

        for company in self:
            company.multi_company_currency_enable = 1 if company_currency > 1 else 0

    @api.multi
    def button_refresh_currency(self):
        """Refresh the currencies rates !!for all companies now"""
        self.services_to_use.refresh_currency()

res_company()


class ResCurrency(models.Model):

    _inherit = 'res.currency'

    def get_url(self, url):
        """Return a string of a get url query"""
        try:
            import urllib2
            opener = urllib2.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            response = opener.open(url)
            rawfile = response.read()
            return rawfile
        except ImportError:
            raise exceptions.UserError(
                'Unable to import urllib !'
            )
        except IOError:
            raise exceptions.UserError(
                'Web Service does not exist !'
            )

    @api.multi
    def fetch_history(self):
        self.ensure_one()
        if self.name == 'EUR':
            return
        self.env['res.currency.rate'].search([('currency_id', '=', self.id)]).unlink()
        url = 'http://lb.lt/fxrates_csv.lb?tp=LT&rs=&dts=%s&dte=%s&ccy=%s&ln=lt'
        nuo = datetime(datetime.now().year-1, 1, 1)
        iki = datetime.now()
        res = self.get_url(url % (nuo.strftime('%Y-%m-%d'), iki.strftime('%Y-%m-%d'), self.name))
        for line in res.split('\n'):
            cols = line.split(',')
            if not cols:
                continue
            try:
                val = float(cols[2])
            except:
                continue
            if val:
                self.env['res.currency.rate'].create({
                    'currency_id': self.id,
                    'name': cols[3],
                    'rate': val,
                })
            else:
                raise Exception('Could not update the %s' % self.name)

ResCurrency()
