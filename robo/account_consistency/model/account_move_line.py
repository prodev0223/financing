# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMoveLine(models.Model):
    """
    Extension contains new fields that are only used
    for consistency checking between stock and accounting.
    Does not make sense to add them to other modules
    """
    _inherit = 'account.move.line'

    write_off_invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra')
    write_off_invoice_line_id = fields.Many2one('account.invoice.line', string='Sąskaitos faktūros eilutė')


AccountMoveLine()
