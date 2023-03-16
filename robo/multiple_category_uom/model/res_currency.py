# -*- encoding: utf-8 -*-

from odoo import models, api
import decimal


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.multi
    def apply_currency_rounding(self, value):
        """
        Check whether currency rounding should be applied
        while converting passed value
        If passed value exponent is higher, it should not be applied
        :param value: passed value (float)
        :return: True/False
        """
        self.ensure_one()
        price_exponent = abs(decimal.Decimal(str(value)).as_tuple().exponent)
        currency_exponent = abs(decimal.Decimal(str(self.rounding)).as_tuple().exponent)
        return price_exponent <= currency_exponent
