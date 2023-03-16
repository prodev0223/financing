# -*- coding: utf-8 -*-

import ast

from odoo import _, api, exceptions, fields, models
from .res_company import APPROVAL_DEADLINE_REACHED_ACTIONS


class InvoiceApprovalStep(models.Model):
    _name = 'invoice.approval.step'
    _inherit = ['mail.thread']

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(required=True, help="The sequence in which to follow the workflow.",
                              inverse='_normalise_sequences')

    condition_ids = fields.One2many('invoice.approval.condition', 'step_id', string='Conditions')
    approval_condition = fields.Selection(
        [('all', 'All approvers have to approve'), ('number_of_approvers', 'Some approvers have to approve')],
        string='Approval condition',
        required=True,
        default='all'
    )
    approvals_needed = fields.Integer(string='Number of approvals to approve', default=1)
    default_approver = fields.Many2one('invoice.approver', string='Default approver',
                                       help='Who should approve an invoice for this step when no approvers are matched')
    condition_number = fields.Integer(string='Number of conditions', compute='_compute_condition_number')
    deadline_days = fields.Integer(string='Deadline (days)', default=0)
    deadline_hours = fields.Integer(string='Deadline (hours)', default=0)
    deadline_reached_action = fields.Selection(
        APPROVAL_DEADLINE_REACHED_ACTIONS, string='Action after deadline has been reached',
        default='do_nothing', help='What happens after the deadline has been reached'
    )

    @api.model
    def default_get(self, fields_list):
        res = super(InvoiceApprovalStep, self).default_get(fields_list)
        sequences = self.search([]).mapped('sequence')
        if sequences:
            res['sequence'] = max(sequences) + 1
        else:
            res['sequence'] = 1
        return res

    @api.multi
    @api.constrains('sequence')
    def _check_sequence_greater_than_zero(self):
        sequences = self.mapped('sequence')
        if sequences and min(sequences) <= 0:
            raise exceptions.UserError(_('Approval step sequence must be greater than 0'))

    @api.multi
    @api.constrains('deadline_days', 'deadline_hours')
    def _check_deadline_is_not_negative(self):
        for rec in self:
            if rec.deadline_days and rec.deadline_days < 0:
                raise exceptions.ValidationError(_('Deadline (days) must be greater or equal to zero'))
            if rec.deadline_hours and rec.deadline_hours < 0:
                raise exceptions.ValidationError(_('Deadline (hours) must be greater or equal to zero'))

    @api.multi
    def _normalise_sequences(self):
        if self._context.get('bypass_sequence_update'):
            return
        records = self.search([]).sorted(key=lambda rec: rec.sequence)
        sequence_adjusted = 1
        for rec in records:
            # Prevent recursion and update the sequence
            rec.with_context(bypass_sequence_update=True).sequence = sequence_adjusted
            sequence_adjusted += 1

    @api.multi
    @api.constrains('approvals_needed')
    def _check_approvals_needed(self):
        for rec in self:
            if rec.approvals_needed < 0:
                raise exceptions.ValidationError(_('Number of approvers needed can not be a negative number'))

    @api.multi
    def toggle_active(self):
        """ Inverse the value of the field ``active`` on the records in ``self``. """
        for record in self:
            record.active = not record.active

    @api.multi
    @api.depends('condition_ids')
    def _compute_condition_number(self):
        for rec in self:
            rec.condition_number = len(rec.condition_ids)

    @api.multi
    def action_open_approval_conditions(self):
        self.ensure_one()
        action = self.env.ref('invoice_approval_workflow.invoice_approval_condition_action')
        action = action.read()[0]
        domain = action.get('domain') or list()
        domain.append(('step_id', 'in', self.ids))
        action['domain'] = domain
        context = ast.literal_eval(action['context'])
        context.update({'active_approval_step_id': self.id})
        action['context'] = context
        return action


InvoiceApprovalStep()
