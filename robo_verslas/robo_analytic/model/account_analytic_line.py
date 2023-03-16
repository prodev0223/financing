# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions, _


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita', compute='_compute_invoice_id')

    @api.multi
    def _compute_invoice_id(self):
        for rec in self:
            if rec.move_id:
                rec.invoice_id = rec.move_id.invoice_id

    def action_open_shared_business_analytics(self):
        has_shared_analytics_access = self.env.user.has_group('robo_analytic.group_robo_business_analytic_sharing')
        if not has_shared_analytics_access:
            raise exceptions.UserError(_('You do not have sufficient rights'))

        action = self.env.ref('robo_analytic.action_shared_business_analytics', False)
        if action:
            action = action.read()[0]
            analytic_accounts = self.env['project.involvement'].sudo().search([
                ('user_id', '=', self.env.user.id)
            ]).mapped('analytic_account_id')
            action['domain'] = [('account_id', 'in', analytic_accounts.ids), '|',
                                ('general_account_id.code', '=ilike', '5%'),
                                ('general_account_id.code', '=ilike', '6%')]
            return action
