# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, fields, models


class DisapproveAccountInvoice(models.TransientModel):
    _name = 'disapprove.account.invoice'

    @api.model
    def _get_workflow_id(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        return active_id

    workflow_step_id = fields.Many2one('invoice.approval.workflow.step', string='Workflow step', required=True,
                                       default=_get_workflow_id, ondelete='cascade')
    workflow_step_approver_id = fields.Many2one('invoice.approval.workflow.step.approver', string='Workflow approver',
                                                compute='_compute_workflow_step_approver_id')
    reason = fields.Text(string='Reason for disapproval', required=True)

    @api.multi
    def _compute_workflow_step_approver_id(self):
        user = self.env.user
        for rec in self:
            workflow_step = rec.workflow_step_id
            matched_approver_id = workflow_step.matched_approver_ids.filtered(
                lambda approver: approver.approver_id.user_id == user
            )
            if matched_approver_id:
                matched_approver_id = matched_approver_id[0]
            rec.workflow_step_approver_id = matched_approver_id

    @api.multi
    def action_disapprove(self):
        self.ensure_one()
        if not self.workflow_step_id:
            raise exceptions.UserError(_('Could not determine the workflow step the disapproval is for'))
        if not self.workflow_step_approver_id:
            raise exceptions.UserError(_('You are not allowed to disapprove this invoice for this workflow step'))
        if not self.reason:
            raise exceptions.UserError(_('You must enter a reason for your disapproval.'))

        self.workflow_step_id._set_matched_approver_approval_decision('disapproved', self.reason)

    @api.multi
    def action_force_disapprove(self):
        self.ensure_one()
        if not self.workflow_step_id:
            raise exceptions.UserError(_('Could not determine the workflow step the disapproval is for'))
        if not self.reason:
            raise exceptions.UserError(_('You must enter a reason for your disapproval.'))
        self.workflow_step_id.workflow_id._force_set_decision('disapproved', self.reason)


DisapproveAccountInvoice()
