# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _


class FrontBankStatementLine(models.Model):
    _name = 'front.bank.statement.line'
    _inherit = ['account.bank.statement.line']

    statement_id = fields.Many2one(
        'front.bank.statement', string='Bankinis išrašas',
        required=True, readonly=True, ondelete='cascade'
    )
    name = fields.Char(help='Laukelis Naudojamas kaip mokėjimo paskirtis')

    # Bank export data fields
    bank_export_job_ids = fields.One2many(
        'bank.export.job', 'front_statement_line_id',
        string='Banko eksporto darbai'
    )

    @api.multi
    @api.constrains('amount')
    def _check_amount(self):
        """Ensure that amount is always with a negative sign"""
        for rec in self:
            if tools.float_compare(0.0, rec.amount, precision_digits=2) < 0:
                raise exceptions.UserError(_('Transaction amount must be negative!'))
