# -*- coding: utf-8 -*-
import time

from odoo import models, exceptions, api
from odoo.tools.translate import _


class ResCurrency(models.Model):

    _inherit = 'res.currency'

    @api.model
    def _get_conversion_rate(self, from_currency, to_currency):
        if 'revaluation' in self._context:
            rate = from_currency.rate
            if rate == 0.0:
                date = self._context.get('date', time.strftime('%Y-%m-%d'))
                raise exceptions.Warning(_('No rate found \n'
                                           'for the currency: %s \n'
                                           'at the date: %s') %
                                         (from_currency.symbol, date))
            return 1.0 / rate

        else:
            return super(ResCurrency, self)._get_conversion_rate(from_currency, to_currency)


ResCurrency()
