# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    gpais_tiekimas = fields.Selection([('mazmenine', 'Mažmeninė prekyba'),
                                       ('didmenine', 'Didmeninė prekyba'),
                                       ('nuotolinė', 'Nuotolinė prekyba'),
                                       ('tretieji', 'Per trečiuosius asmenis')], string='Veiklos būdas (GPAIS)')
