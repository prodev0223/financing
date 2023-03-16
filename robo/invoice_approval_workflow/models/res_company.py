# -*- coding: utf-8 -*-

from odoo import fields, models, api, _

SAFETY_NET_ACTIONS = [
    ('approve', 'Automatically approve'),
    ('disapprove', 'Automatically disapprove'),
    ('send_for_approval', 'Send for approval')
]

SAFETY_NET_CONDITIONS_NOT_MATCHED_ACTIONS = [
    ('approve', 'Approve'),
    ('disapprove', 'Disapprove'),
]

APPROVAL_DEADLINE_REACHED_ACTIONS = [
    ('approve', 'Automatically approve'),
    ('disapprove', 'Automatically disapprove'),
    ('do_nothing', 'Do nothing')
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    module_invoice_approval_workflow = fields.Boolean(string='Enable invoice approval',
                                                      inverse='_set_module_invoice_approval_workflow')
    safety_net_action = fields.Selection(SAFETY_NET_ACTIONS, string='Safety net action',
                                         help='What happens when there is no one to review an invoice',
                                         default='approve')
    sn_approvers = fields.Many2many('invoice.approver', string='Safety net approvers')
    safety_net_approval_deadline_days = fields.Integer(string='Safety net deadline (days)', default=0)
    safety_net_approval_deadline_hours = fields.Integer(string='Safety net deadline (hours)', default=0)
    safety_net_deadline_reached_action = fields.Selection(
        APPROVAL_DEADLINE_REACHED_ACTIONS, string='Action after safety net deadline has been reached',
        default='do_nothing',
        help='What happens when there has been no action taken after the safety net deadline has been reached',
    )
    apply_safety_net_conditions = fields.Boolean('Apply additional safety net conditions',
                                                 compute='_compute_apply_safety_net_conditions',
                                                 inverse='_set_apply_safety_net_conditions')
    action_not_matching_conditions = fields.Selection(
        SAFETY_NET_CONDITIONS_NOT_MATCHED_ACTIONS,
        string='Action to perform if invoice does not match any of the approval conditions',
        compute='_compute_action_not_matching_conditions', inverse='_set_action_not_matching_conditions')

    @api.multi
    def _set_module_invoice_approval_workflow(self):
        self.ensure_one()  # There should be only one res.company
        if self.module_invoice_approval_workflow:
            self.env['account.invoice'].sudo().search([
                ('type', 'in', ['in_invoice', 'in_refund']),
                ('state', 'in', ['open', 'paid']),
                ('approval_workflow_ids', '=', False),
                ('approved', '=', False),
            ]).write({'approved': True})
        else:
            invoices = self.env['account.invoice'].sudo().search([
                ('approval_workflow_ids', '!=', False),
                '|',
                ('state', '=', 'in_approval'),
                ('expense_state', '=', 'in_approval')
            ])
            workflows = invoices.mapped('approval_workflow_ids').filtered(lambda workflow: not workflow.decision)
            for workflow in workflows:
                workflow.sudo()._force_set_decision(
                    'disapproved', _('Invoice approval has been disabled. Cancelling all waiting approvals.')
                )
        invoice_approval_group = self.env.ref('invoice_approval_workflow.invoice_approval_enabled_group')
        approval_user_group = self.env.ref('invoice_approval_workflow.invoice_approval_auditor')
        approval_user_group_users = approval_user_group.mapped('users')
        accountants = self.env.ref('robo_basic.group_robo_premium_accountant').mapped('users')
        operator = 4 if self.module_invoice_approval_workflow else 3
        users_to_update = accountants + approval_user_group_users
        users_to_update.sudo().write({'groups_id': [(operator, invoice_approval_group.id,),]})

    @api.multi
    def _compute_apply_safety_net_conditions(self):
        self.ensure_one()
        apply_safety_net_conditions = self.env['ir.config_parameter'].sudo().get_param('apply_safety_net_conditions')
        self.apply_safety_net_conditions = apply_safety_net_conditions == 'True'

    @api.multi
    def _set_apply_safety_net_conditions(self):
        self.ensure_one()
        value = str(self.apply_safety_net_conditions)
        self.env['ir.config_parameter'].sudo().set_param('apply_safety_net_conditions', value)

    @api.multi
    def _compute_action_not_matching_conditions(self):
        self.ensure_one()
        self.action_not_matching_conditions = self.env['ir.config_parameter'].sudo().get_param(
            'action_not_matching_conditions') or 'disapprove'

    @api.multi
    def _set_action_not_matching_conditions(self):
        self.ensure_one()
        value = str(self.action_not_matching_conditions)
        self.env['ir.config_parameter'].sudo().set_param('action_not_matching_conditions', value)
