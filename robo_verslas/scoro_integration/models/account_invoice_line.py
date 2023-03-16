# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    scoro_line_id = fields.Many2one('scoro.invoice.line', string='Scoro pardavimų eilutės')


AccountInvoiceLine()
