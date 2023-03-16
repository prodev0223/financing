# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    split_tax = fields.Boolean(string='Mokesčiai jau išskaidyti', default=False)
