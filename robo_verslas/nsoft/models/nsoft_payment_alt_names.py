# -*- coding: utf-8 -*-

from odoo import models, fields


class NsoftPaymentAltNames(models.Model):
    _name = 'nsoft.payment.alt.names'

    pay_type_id = fields.Many2one('nsoft.payment.type')
    alternative_name = fields.Char(string='Alternatyvus pavadinimas')


NsoftPaymentAltNames()
