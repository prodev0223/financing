# -*- coding: utf-8 -*-

from odoo import fields, models, api, _

# https://www.lb.lt/lt/pf-veiklos-rodikliai


class ResPensionFund(models.Model):
    _name = 'res.pension.fund'

    _sql_constraints = [('unique_fund_code', 'unique (fund_code)', _('Pension fund code must be unique'))]

    name = fields.Char(string='Pension fund title', required=True)
    partner_id = fields.Many2one('res.partner', string='Related partner')
    fund_code = fields.Char(string='Fund code', required=True)
    issues = fields.Text(string='Issues', compute='_compute_issues')

    @api.multi
    @api.depends('partner_id', 'partner_id.bank_ids')
    def _compute_issues(self):
        for pension_fund in self:
            issues = ''
            if not pension_fund.partner_id:
                issues += _('No partner linked to the pension fund') + '\n'
            else:
                if not pension_fund.partner_id.bank_ids:
                    issues += _('Missing bank account for linked partner') + '\n'
            pension_fund.issues = issues
