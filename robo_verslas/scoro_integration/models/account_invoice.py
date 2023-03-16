# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    scoro_line_ids = fields.One2many('scoro.invoice.line', 'invoice_id', string='Scoro pardavimų eilutės')
    scoro_invoice_id = fields.Many2one('scoro.invoice', string='Scoro sąskaita')


AccountInvoice()
