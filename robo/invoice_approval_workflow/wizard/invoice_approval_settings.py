# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, fields, models
from ..models.res_company import APPROVAL_DEADLINE_REACHED_ACTIONS, SAFETY_NET_ACTIONS, \
    SAFETY_NET_CONDITIONS_NOT_MATCHED_ACTIONS


class InvoiceApprovalSettings(models.TransientModel):
    _name = 'invoice.approval.settings'
    _description = 'Invoice approval settings'

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
    apply_safety_net_conditions = fields.Boolean('Apply additional safety net conditions')
    safety_net_conditions = fields.Many2many('safety.net.condition', string='Safety net conditions')
    action_not_matching_conditions = fields.Selection(
        SAFETY_NET_CONDITIONS_NOT_MATCHED_ACTIONS, string='Action for invoices not matching safety net conditions',
        help="What happens when the invoice falls under safety net and doesn't match any of the conditions",
        default='disapprove', required=True
    )

    @api.onchange('apply_safety_net_conditions')
    def _onchange_apply_safety_net_conditions_reset_action_not_matching_conditions(self):
        for rec in self:
            if not rec.apply_safety_net_conditions and not rec.action_not_matching_conditions:
                rec.action_not_matching_conditions = 'disapprove'

    @api.model
    def default_get(self, fields):
        res = super(InvoiceApprovalSettings, self).default_get(fields)
        company = self.env.user.sudo().company_id
        is_approval_administrator = self.env.user.has_group('invoice_approval_workflow.invoice_approval_administrator')
        safety_net_conditions = self.env['safety.net.condition'].sudo().search([])
        if is_approval_administrator:
            res.update({
                'safety_net_action': company.safety_net_action,
                'sn_approvers': [(6, 0, company.sn_approvers.ids)],
                'safety_net_approval_deadline_days': company.safety_net_approval_deadline_days,
                'safety_net_approval_deadline_hours': company.safety_net_approval_deadline_hours,
                'safety_net_deadline_reached_action': company.safety_net_deadline_reached_action,
                'apply_safety_net_conditions': company.apply_safety_net_conditions,
                'safety_net_conditions': safety_net_conditions.ids,
                'action_not_matching_conditions': company.action_not_matching_conditions or 'disapprove',
            })
        return res

    @api.multi
    @api.constrains('safety_net_action', 'sn_approvers')
    def _check_sn_approvers(self):
        for rec in self:
            if rec.safety_net_action == 'send_for_approval' and not rec.sn_approvers:
                raise exceptions.UserError(_('Please specify the approver to send the invoice for approval to'))

    @api.multi
    @api.constrains('safety_net_approval_deadline_days', 'safety_net_approval_deadline_hours')
    def _check_deadline_is_positive(self):
        for rec in self:
            if rec.safety_net_approval_deadline_days and rec.safety_net_approval_deadline_days < 0:
                raise exceptions.UserError(_('Safety net deadline (days) must be greater or equal to 0'))
            if rec.safety_net_approval_deadline_hours and rec.safety_net_approval_deadline_hours < 0:
                raise exceptions.UserError(_('Safety net deadline (hours) must be greater or equal to 0'))

    @api.multi
    def save_invoice_approval_settings(self):
        self.ensure_one()
        is_approval_administrator = self.env.user.has_group('invoice_approval_workflow.invoice_approval_administrator')
        if not is_approval_administrator:
            raise exceptions.UserError(_('You do not have sufficient rights to perform this action'))
        company = self.env.user.company_id
        company.sudo().write({
            'safety_net_action': self.safety_net_action,
            'sn_approvers': [(6, 0, self.sn_approvers.ids)],
            'safety_net_approval_deadline_days': self.safety_net_approval_deadline_days,
            'safety_net_approval_deadline_hours': self.safety_net_approval_deadline_hours,
            'safety_net_deadline_reached_action': self.safety_net_deadline_reached_action,
            'apply_safety_net_conditions': self.apply_safety_net_conditions,
            'action_not_matching_conditions': self.action_not_matching_conditions,
        })
        self.env['safety.net.condition'].sudo().search([('id', 'not in', self.safety_net_conditions.ids)]).unlink()
        return self.env.ref('robo.open_robo_vadovas_client_action').read()[0]

    @api.multi
    def cancel(self):
        """Return user to main view"""
        self.ensure_one()
        return self.env.ref('robo.open_robo_vadovas_client_action').read()[0]


InvoiceApprovalSettings()
