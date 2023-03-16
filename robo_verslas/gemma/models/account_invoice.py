# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    gemma_payment_move = fields.Many2one('account.move', string='DK sąskaitos')
    gemma_line_ids = fields.One2many('gemma.sale.line', 'invoice_id', string='Gemma pardavimų eilutės')
    gemma_correction_line_ids = fields.One2many('gemma.sale.line',
                                                'correction_id', string='Gemma pardavimų pataisytos eilutės')
    gemma_refund_line_ids = fields.One2many('gemma.sale.line',
                                            'refund_id', string='Gemma pardavimų anuliuotos eilutės')


AccountInvoice()
