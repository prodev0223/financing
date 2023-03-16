# -*- coding: utf-8 -*-
from odoo import models, fields


class InvoiceAnalyticWizardLineAccountAnalyticLine(models.TransientModel):
    """
    Transient model that is used in invoice.analytic.wizard.line
    wizard, as a simulated account.analytic.line record on force_dates action.
    Changes are made to this record, then, on saving, data is written
    to actual account.analytic.line object.
    """
    _name = 'invoice.analytic.wizard.line.account.analytic.line'

    wizard_id = fields.Many2one('invoice.analytic.wizard.line', ondelete='cascade')
    analytic_line_id = fields.Many2one('account.analytic.line')
    account_id = fields.Many2one('account.account', string='Finansinė sąskaita')

    date = fields.Date(string='Data')
    amount = fields.Float(string='Suma')
    ref = fields.Char(string='Nuoroda')


InvoiceAnalyticWizardLineAccountAnalyticLine()
