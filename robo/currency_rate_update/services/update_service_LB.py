# -*- coding: utf-8 -*-
from .currency_getter_interface import Currency_getter_interface
from datetime import datetime
from suds.client import Client
import urllib2

from suds.transport.https import HttpAuthenticated
from suds.transport import TransportError

class HttpHeaderModify(HttpAuthenticated):
    def open(self, request):
        try:
            url = request.url
            u2request = urllib2.Request(url, headers={'User-Agent': 'Mozilla'})
            self.proxy = self.options.proxy
            return self.u2open(u2request)
        except urllib2.HTTPError as e:
            raise TransportError(str(e), e.code, e.fp)


class LB_getter(Currency_getter_interface):

    def get_updated_currency(self, currency_array, main_currency,
                             max_delta_days):
        """implementation of abstract method of curreny_getter_interface"""
        url = 'https://www.lb.lt/webservices/FxRates/FxRates.asmx?wsdl'
        laikas = datetime.utcnow().date().strftime('%Y-%m-%d')
        if main_currency in currency_array:
            currency_array.remove(main_currency)
        transport = HttpHeaderModify()
        client = Client(url, transport=transport)
        res = client.service.getFxRatesForCurrency(tp='LT', dtFrom=laikas, dtTo=laikas)
        rates = {FxRate.CcyAmt[1].Ccy: float(FxRate.CcyAmt[1].Amt) for FxRate in res.FxRates.FxRate}

        for curr in currency_array:
            val = rates.get(curr)
            if val:
                self.updated_currency[curr] = val
            else:
                raise Exception('Could not update the %s' % curr)

        return self.updated_currency, self.log_info
