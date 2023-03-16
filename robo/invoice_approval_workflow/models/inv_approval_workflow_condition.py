# -*- coding: utf-8 -*-

from odoo import fields, models


class InvApprovalWorkflowCondition(models.Model):
    _name = 'inv.approval.workflow.condition'
    _inherit = 'invoice.approval.condition'

    workflow_approver_id = fields.Many2one('invoice.approval.workflow.step.approver', string='Approver',
                                           ondelete='set null')
    workflow_step_id = fields.Many2one('invoice.approval.workflow.step', string='Workflow step', store=True,
                                       ondelete='cascade')
    approver_id = fields.Many2one(ondelete='set null')


InvApprovalWorkflowCondition()
