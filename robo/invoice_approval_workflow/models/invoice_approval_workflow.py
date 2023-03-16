# -*- coding: utf-8 -*-
import ast
from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class InvoiceApprovalWorkflow(models.Model):
    _name = 'invoice.approval.workflow'
    _inherit = ['mail.thread']

    invoice_id = fields.Many2one('account.invoice', string='Invoice', required=True, ondelete='cascade')
    step_ids = fields.One2many('invoice.approval.workflow.step', 'workflow_id', string='Approval States')
    decision = fields.Selection([('approved', 'Approved'), ('disapproved', 'Disapproved')],
                                string='Decision', compute='_compute_decision', store=True,
                                inverse='_update_invoice_after_decision')
    force_decided = fields.Boolean(string='Force decided')
    invoice_number = fields.Char(string='Invoice number', related='invoice_id.computed_number', readonly=True)
    amount_total_signed = fields.Monetary(string='Invoice amount', related='invoice_id.amount_total_signed',
                                          readonly=True)
    amount_total_company_signed = fields.Monetary(string='Invoice amount company currency',
                                                  related='invoice_id.amount_total_company_signed', readonly=True)
    invoice_supplier = fields.Many2one('res.partner', string='Invoice supplier', related='invoice_id.partner_id',
                                       readonly=True)
    invoice_submitted = fields.Char(string='Invoice submitted by', related='invoice_id.submitted', readonly=True)
    invoice_pdf = fields.Binary(string='Invoice pdf', related='invoice_id.pdf', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Invoice Currency', related='invoice_id.currency_id',
                                  readonly=True)
    company_currency_id = fields.Many2one('res.currency', related='invoice_id.company_currency_id', readonly=True)
    allow_performing_approval_action = fields.Boolean(compute='_compute_allow_performing_approval_action')
    method_to_execute_on_approval = fields.Char(name='Method to be executed on workflow approval', readonly=True)
    date_invoice = fields.Date(string='Date invoice', related='invoice_id.date_invoice', readonly=True)
    invoice_reference = fields.Char(string='Reference', related='invoice_id.reference', readonly=True)
    invoice_line_ids = fields.Many2many('account.invoice.line', string='Invoice lines',
                                        compute='_compute_invoice_line_ids', readonly=True)
    waiting_for_text = fields.Char('Waiting for', compute='_compute_waiting_for_text', compute_sudo=True)
    date_decision_made = fields.Datetime('Decision date', readonly=True)

    @api.multi
    @api.depends('invoice_id', 'invoice_id.invoice_line_ids')
    def _compute_invoice_line_ids(self):
        for rec in self.filtered(lambda ws: ws.invoice_id):
            rec.invoice_line_ids = [(6, 0, rec.invoice_id.invoice_line_ids.ids)]

    @api.multi
    @api.depends('decision')
    def _compute_allow_performing_approval_action(self):
        for rec in self:
            rec.allow_performing_approval_action = not rec.decision

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            name = rec.invoice_id.reference or rec.invoice_id.number or rec.invoice_id.proforma_number
            if not name:
                name = _('Invoice')
            name += _(' approval')
            res.append((rec.id, name))
        return res

    @api.multi
    @api.depends('step_ids.decision_made')
    def _compute_decision(self):
        for rec in self:
            steps = rec.step_ids
            steps_with_approvers = steps.filtered(lambda step: step.number_of_approvers >= 1)
            if not steps:
                rec.decision = 'approved'
            else:
                if any(step.decision_made == 'disapproved' for step in steps):
                    rec.decision = 'disapproved'
                elif all(step.decision_made == 'approved' for step in steps_with_approvers):
                    rec.decision = 'approved'
                else:
                    rec.decision = False

    @api.multi
    @api.depends('step_ids', 'step_ids.sequence', 'step_ids.matched_approver_ids',
                 'step_ids.matched_approver_ids.approval_decision', 'step_ids.decision_made')
    def _compute_waiting_for_text(self):
        number_of_approvers_to_show = 5
        for rec in self:
            steps_waiting_for_action = rec.step_ids.filtered(lambda step: step.action_needed)
            if not steps_waiting_for_action or rec.decision:
                rec.waiting_for_text = '-'
                continue
            elif len(steps_waiting_for_action) > 1:
                next_step = steps_waiting_for_action.sorted(key=lambda step: step.sequence)[0]
            else:
                next_step = steps_waiting_for_action

            next_step_approvers = next_step.mapped('matched_approver_ids')
            approvers_waiting_for = next_step_approvers.filtered(lambda approver:
                                                                 not approver.approval_decision).mapped('approver_id')
            if not approvers_waiting_for:
                approvers_waiting_for = next_step.default_approver

            if not approvers_waiting_for:
                rec.waiting_for_text = '-'
                continue

            approver_users = approvers_waiting_for.sudo().mapped('user_id')
            user_names = approver_users.mapped('name')
            waiting_for_text = ', '.join(user_names[:number_of_approvers_to_show])
            number_of_other_users = max(len(user_names) - number_of_approvers_to_show, 0)
            if number_of_other_users > 0:
                waiting_for_text += _(' +{} others').format(number_of_other_users)
            rec.waiting_for_text = waiting_for_text

    @api.multi
    def _force_set_decision(self, decision, reason=None):
        user = self.env.user
        is_approval_administrator = user.has_group('invoice_approval_workflow.invoice_approval_administrator')
        if not is_approval_administrator:
            raise exceptions.UserError(_('You are not allowed to force approve invoices'))
        workflows = self.filtered(lambda r: not r.decision)
        # Update workflow with the decision but do not leave a decision comment just yet
        workflows.with_context(do_not_leave_a_decision_comment=True).write({
            'force_decided': True,
            'decision': decision
        })
        workflow_steps = workflows.mapped('step_ids')
        workflow_steps.write({'action_needed': False})
        workflow_steps.filtered(lambda step: not step.decision_made).write({'decision_made': decision})

        # Leave comments
        forced_decision_comment = _('{}{} has force {} this invoice.').format(
            user.name,
            (' ' + _('(Accountant)')) if user.is_accountant() else '',
            _('approved') if decision == 'approved' else _('disapproved')
        )
        for workflow in workflows:
            for workflow_step in workflow.mapped('step_ids'):
                workflow_step._leave_comment(forced_decision_comment)
            workflow._leave_decision_comment(reason)

    @api.multi
    def action_approve(self):
        self._force_set_decision('approved')

    @api.multi
    def action_disapprove(self):
        return self._open_invoice_force_disapproval_wizard()

    @api.multi
    def _open_invoice_force_disapproval_wizard(self):
        self.ensure_one()
        action = self.env.ref('invoice_approval_workflow.force_disapprove_account_invoice_action')
        action = action.read()[0]
        context = ast.literal_eval(action['context'])
        # Step is only necessary to determine the workflow id. The disapprove account invoice wizard was designed to
        # handle workflow steps
        active_steps = self.step_ids
        if not active_steps:
            raise exceptions.UserError(_('Unexpected error, the invoice that you are trying to disapprove does not '
                                         'have any steps. Contact the system administrators'))
        context['active_id'] = active_steps[0].id
        action['context'] = context
        return action

    @api.multi
    def _update_invoice_after_decision(self):
        for rec in self:
            if not rec.decision:
                continue
            elif rec.decision == 'disapproved':
                rec.sudo().invoice_id.action_invoice_cancel()
            elif rec.decision == 'approved':
                rec.sudo().invoice_id.write({'approved': True})
                try:
                    method_to_call = getattr(rec.sudo().invoice_id, rec.method_to_execute_on_approval)
                except AttributeError:
                    method_to_call = None
                except TypeError:
                    method_to_call = None
                rec.sudo().invoice_id.write({'state': 'draft'})
                if method_to_call:
                    method_to_call()
            if not self._context.get('do_not_leave_a_decision_comment'):
                rec._leave_decision_comment()
            rec.sudo().write({'date_decision_made': datetime.utcnow()})

    @api.multi
    def _leave_decision_comment(self, reason=None):
        self.ensure_one()
        decision = self.decision
        if not decision:
            raise exceptions.UserError(_('Can not leave a decision comment if no decision has been made'))

        user = self.env.user

        if self.force_decided:
            body = _('{} has force {} this invoice.').format(
                user.name,
                _('approved') if decision == 'approved' else _('disapproved')
            )
        else:
            body = _('The invoice {} the invoice approval workflow.').format(
                _('has passed') if decision == 'approved' else _('did not pass')
            )

        if self.force_decided and decision != 'approved':
            if not reason:
                raise exceptions.UserError(_('Can not leave a decision comment with out the decision reason if the '
                                             'decision is not for the approval of the workflow step'))
            body += _(' Reason: {}').format(reason)

        msg = {
            'body': body,
            'front_message': True,
            'rec_model': 'invoice.approval.workflow',
            'rec_id': self.id,
            'subtype': 'robo.mt_robo_front_message'
        }
        self.sudo().robo_message_post(**msg)
        msg = {
            'body': body,
            'front_message': True,
            'rec_model': 'account.invoice',
            'rec_id': self.invoice_id.id,
            'subtype': 'robo.mt_robo_front_message'
        }
        self.sudo().invoice_id.robo_message_post(**msg)

    @api.model
    def cron_manage_deadlines(self):
        workflow_steps_with_deadlines = self.env['invoice.approval.workflow.step'].search([
            ('deadline', '!=', False),
            ('deadline_action_executed', '=', False)
        ])

        now = datetime.utcnow()

        workflows_to_update = self

        for workflow_step in workflow_steps_with_deadlines:
            if workflow_step.deadline <= now.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT):
                workflow_step_vals = {}
                if not workflow_step.deadline_reached:
                    workflow_step_vals['deadline_reached'] = True
                if not workflow_step.decision_made:
                    workflow_step_vals['deadline_action_executed'] = True
                    comment = _('This workflow step has been automatically {} because the approval deadline has passed')
                    if workflow_step.deadline_reached_action == 'approve':
                        workflow_step_vals['decision_made'] = 'approved'
                        workflow_step._leave_comment(comment.format(_('approved')))
                        workflows_to_update |= workflow_step.workflow_id
                    elif workflow_step.deadline_reached_action == 'disapprove':
                        workflow_step_vals['decision_made'] = 'disapproved'
                        workflow_step._leave_comment(comment.format(_('disapproved')))
                        workflows_to_update |= workflow_step.workflow_id
                if workflow_step_vals:
                    workflow_step.write(workflow_step_vals)

        workflows_to_update._update_invoice_after_decision()

    @api.multi
    @api.returns('self', lambda value: value.id)
    def robo_message_post(self, **kwargs):
        """
        Overridden method posts message on all workflow step records of the current workflow
        """
        is_comment = kwargs.get('message_type') == 'notification' and kwargs.get('subtype') == 'mail.mt_note'
        if is_comment:
            steps = self.mapped('step_ids')
            for step in steps:
                step.with_context(prevent_recursion=True).robo_message_post(**kwargs)
        return super(InvoiceApprovalWorkflow, self).robo_message_post(**kwargs)

    @api.model
    def create_workflow_approve_action(self):
        action = self.env.ref('invoice_approval_workflow.invoice_approval_workflow_approve')
        if action:
            action.create_action()
