# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    proforma_print_commercial_offer = fields.Boolean(string='Print Commercial Offer', sequence=100)
