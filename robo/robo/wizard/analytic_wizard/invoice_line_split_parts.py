# -*- coding: utf-8 -*-
from odoo import models, fields


class InvoiceLineSplitParts(models.TransientModel):
    """
    Transient model that is used in invoice.line.change wizard
    on split line action.
    """
    _name = 'invoice.line.split.parts'

    wiz_id = fields.Many2one('invoice.analytic.wizard.line', ondelete='cascade')
    account_analytic_id = fields.Many2one('account.analytic.account',
                                          string='Analitinė sąskaita', ondelete='cascade')
    amount = fields.Float(string='Eilutės suma')


InvoiceLineSplitParts()
