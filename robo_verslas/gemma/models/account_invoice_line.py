# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'
    gemma_sale_line_ids = fields.One2many('gemma.sale.line',
                                          'invoice_line_id', string='Gemma pardavimų eilutės')
    gemma_correction_line_ids = fields.One2many('gemma.sale.line',
                                                'correction_line_id', string='Gemma pataisytos eilutės')
    gemma_refund_line_ids = fields.One2many('gemma.sale.line',
                                            'refund_line_id', string='Gemma anuliuotos eilutės')


AccountInvoiceLine()
