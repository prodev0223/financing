# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _
from odoo.addons.queue_job.job import job


class AccountMove(models.Model):
    _inherit = 'account.move'

    offsetting_front_move = fields.Boolean(string='Užskaita')
    state = fields.Selection(track_visibility='onchange')

    @api.multi
    @api.constrains('line_ids', 'state')
    def _check_line_state_integrity(self):
        """Ensure that account move cannot be posted if it contains no lines"""
        for rec in self:
            if rec.state == 'posted' and not rec.line_ids:
                raise exceptions.ValidationError(
                    _('You cannot post an account move without any entries.')
                )

    @api.model
    def cancel_moves_func(self):
        action = self.env.ref('robo.cancel_moves_action')
        if action:
            action.create_action()

    @api.multi
    def post(self):
        """
        Apply analytic default rules
        to all passed account_move_line records:
        [   without an analytical code,
            account_id is not related to payslips/salary,
            is related to 5th and 6th class
        ]
        if no default rule is found for specific line -
        assign the company analytic code to the line

        :return: Return/call to parent function
        """

        res = super(AccountMove, self).post()
        AnalyticDefault = self.env['account.analytic.default'].sudo()
        if not self._context.get('skip_analytics', False):
            company = self.sudo().env.user.company_id
            analytic_id = company.analytic_account_id.id
            account_excluded_ids = AnalyticDefault.get_account_ids_to_exclude()
            for rec in self.sudo():
                account_move_lines = rec.line_ids.filtered(
                    lambda r: not r['analytic_account_id'] and r['account_id']['id']
                              not in account_excluded_ids)

                for line in account_move_lines:
                    analytic_def = AnalyticDefault.account_get(partner_id=line.partner_id.id,
                                                               company_id=rec.company_id.id,
                                                               journal_id=line.journal_id.id,
                                                               account_id=line.account_id.id,
                                                               product_id=line.product_id.id,
                                                               date=line.date)

                    line.write({
                        'analytic_account_id': analytic_def.analytic_id.id or analytic_id,
                        'forced_analytic_default': analytic_def.force_analytic_account
                    })
                account_move_lines.create_analytic_lines()

        return res

    @api.multi
    def button_cancel(self):
        res = super(AccountMove, self).button_cancel()
        self.mapped('line_ids.analytic_line_ids').with_context(ensure_analytic_batch_integrity=True).unlink()
        return res

    @job
    @api.multi
    def action_move_cancel_unlink(self):
        if all(not x.reconciled for x in self.line_ids):
            self.button_cancel()
            self.unlink()
