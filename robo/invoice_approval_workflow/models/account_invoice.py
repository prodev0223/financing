# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    approval_workflow_ids = fields.One2many('invoice.approval.workflow', 'invoice_id', string='Approval workflow',
                                            readonly=True, copy=False, sequence=100,
                                            )
    expense_state = fields.Selection(selection_add=[('in_approval', 'In approval')])
    state = fields.Selection(selection_add=[('in_approval', 'In approval')])
    approved = fields.Boolean(string='Invoice has been approved', copy=False, readonly=True)
    allow_performing_approval_action = fields.Boolean(compute='_compute_allow_performing_approval_action')
    allow_performing_force_approval_action = fields.Boolean(compute='_compute_allow_performing_force_approval_action')
    invoice_approval_workflow = fields.Many2one('invoice.approval.workflow',
                                                compute='_compute_invoice_approval_workflow')
    invoice_approval_workflow_step = fields.Many2one('invoice.approval.workflow.step', string='Invoice approval step',
                                                     compute='_compute_invoice_approval_workflow_step')
    invoice_approval_is_enabled = fields.Boolean(compute='_compute_invoice_approval_is_enabled')

    @api.multi
    @api.depends('state', 'approval_workflow_ids')
    def _compute_invoice_approval_workflow(self):
        for rec in self:
            if rec.state != 'in_approval' or not rec.approval_workflow_ids:
                rec.invoice_approval_workflow = False
            else:
                approval_step = rec._find_current_invoice_approval_workflow_step()
                rec.invoice_approval_workflow = approval_step.workflow_id if approval_step else False

    @api.multi
    @api.depends('state', 'approval_workflow_ids')
    def _compute_invoice_approval_workflow_step(self):
        for rec in self:
            if rec.state != 'in_approval' or not rec.approval_workflow_ids:
                rec.invoice_approval_workflow_step = False
            else:
                rec.invoice_approval_workflow_step = rec._find_current_invoice_approval_workflow_step()

    @api.multi
    @api.depends('company_id')
    def _compute_invoice_approval_is_enabled(self):
        for rec in self:
            rec.invoice_approval_is_enabled = rec.sudo().company_id.module_invoice_approval_workflow

    @api.multi
    def _allow_approval_bypass_for_accountant(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            return False
        return self._last_approval_workflow_was_approved()

    @api.multi
    def action_invoice_open(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        bypass_approval = self._allow_approval_bypass_for_accountant()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        in_invoice = self.type in ['in_invoice', 'in_refund']
        is_proforma = self.state in ['proforma2', 'proforma']
        if not invoice_approval_is_active or not in_invoice or self.approved or is_proforma or bypass_approval:
            if not self.approved and self._last_approval_workflow_was_approved() and invoice_approval_is_active:
                self.sudo().write({'approved': True})
            return super(AccountInvoice, self).action_invoice_open()
        else:
            self._check_invoice_open_constraints()
            self._prepare_invoice_for_approval_workflow('action_invoice_open')

    @api.multi
    def action_invoice_proforma2(self):
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if not invoice_approval_is_active:
            return super(AccountInvoice, self).action_invoice_proforma2()

        for rec in self:
            rec._ensure_invoice_not_in_approval()
            bypass_approval = rec._allow_approval_bypass_for_accountant()
            in_invoice = rec.type in ['in_invoice', 'in_refund']
            if rec.approved or bypass_approval or not in_invoice:
                if not rec.approved and rec._last_approval_workflow_was_approved():
                    rec.sudo().write({'approved': True})
                return super(AccountInvoice, rec).action_invoice_proforma2()
            else:
                rec._check_proforma2_constraints()
                rec._prepare_invoice_for_approval_workflow('action_invoice_proforma2')

    @api.multi
    def representation_check(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        bypass_approval = self._allow_approval_bypass_for_accountant()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        in_invoice = self.type in ['in_invoice', 'in_refund']
        is_draft = self.expense_state == 'draft'
        if not invoice_approval_is_active or not in_invoice or self.approved or not is_draft or bypass_approval:
            return super(AccountInvoice, self).representation_check()
        else:
            self._check_invoice_open_constraints()
            self._prepare_invoice_for_approval_workflow('representation_check')

    @api.multi
    def submit_ceo_action(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        bypass_approval = self._allow_approval_bypass_for_accountant()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        in_invoice = self.type in ['in_invoice', 'in_refund']
        is_draft = self.expense_state == 'draft'
        if not invoice_approval_is_active or not in_invoice or self.approved or not is_draft or bypass_approval:
            return super(AccountInvoice, self).submit_ceo_action()
        else:
            self._prepare_invoice_for_approval_workflow('submit_ceo_action')

    @api.multi
    def ask_payment(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        bypass_approval = self._allow_approval_bypass_for_accountant()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if self.approved or bypass_approval or not invoice_approval_is_active:
            return super(AccountInvoice, self).ask_payment()
        else:
            raise exceptions.UserError(_('You can not perform this action until the invoice has been approved'))

    @api.multi
    def ask_representation(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        bypass_approval = self._allow_approval_bypass_for_accountant()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if self.approved or bypass_approval or not invoice_approval_is_active:
            return super(AccountInvoice, self).ask_representation()
        else:
            raise exceptions.UserError(_('You can not perform this action until the invoice has been approved'))

    @api.multi
    def action_invoice_open_type_change_wizard(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        is_draft = self.expense_state == 'draft'
        if invoice_approval_is_active and self.approved and not is_draft:
            raise exceptions.UserError(_('You can not perform this action because the invoice has been approved'))
        return super(AccountInvoice, self).action_invoice_open_type_change_wizard()

    @api.multi
    def action_invoice_open_partner_change_wizard(self):
        self.ensure_one()
        self._ensure_invoice_not_in_approval()
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        is_draft = self.expense_state == 'draft'
        if invoice_approval_is_active and self.approved and not is_draft:
            raise exceptions.UserError(_('You can not perform this action because the invoice has been approved'))
        return super(AccountInvoice, self).action_invoice_open_partner_change_wizard()

    @api.multi
    def _ensure_invoice_not_in_approval(self):
        self.ensure_one()
        if self.state == 'in_approval':
            raise exceptions.UserError(_('Invoice {} is waiting for approval. You can not perform this action until '
                                         'the invoice has been approved').format(self.reference or self.number))

    @api.multi
    def _prepare_invoice_for_approval_workflow(self, callback=None):
        self.ensure_one()
        approval_workflow = self.sudo()._set_up_approval_workflow()
        if callback:
            approval_workflow.sudo().write({'method_to_execute_on_approval': callback})
        if not approval_workflow.step_ids.filtered(lambda step: step.action_needed):
            company = self.env.user.sudo().company_id
            if company.safety_net_action == 'approve':
                approval_workflow.sudo().write({'decision': 'approved'})
            elif company.safety_net_action == 'send_for_approval':
                # Create a safety net workflow step
                deadline = False
                if company.safety_net_approval_deadline_days or company.safety_net_approval_deadline_hours:
                    now = datetime.utcnow()
                    deadline = now + relativedelta(days=company.safety_net_approval_deadline_days,
                                                   hours=company.safety_net_approval_deadline_hours)

                # Check if there are any safety net conditions that should be matched
                extra_conditions = company.apply_safety_net_conditions and \
                                      self.env['safety.net.condition'].sudo().search([])
                matches_any_conditions = True
                if extra_conditions:
                    matches_any_conditions = bool(extra_conditions.filtered(
                        lambda c: c.sudo()._invoice_matches_condition(self)
                    ))

                if matches_any_conditions:
                    # Invoice matches some conditions (or no conditions exist) so it should be approved
                    self.env['invoice.approval.workflow.step'].sudo().create({
                        'name': _('Safety net approval'),
                        'workflow_id': approval_workflow.id,
                        'matched_approver_ids': [(5, 0)] + [
                            (0, 0, {'approver_id': sn_approver.id}) for sn_approver in company.sn_approvers
                        ],
                        'action_needed': True,
                        'deadline': deadline,
                        'deadline_reached_action': company.safety_net_deadline_reached_action
                    })
                else:
                    # Invoice does not match any of the specified safety net conditions so the appropriate automatic
                    # action should be taken
                    decision = 'approved' if company.action_not_matching_conditions == 'approve' else 'disapproved'
                    approval_workflow.sudo().write({'decision': decision})
            else:
                approval_workflow.sudo().write({'decision': 'disapproved'})

    @api.multi
    def _last_approval_workflow_was_approved(self):
        self.ensure_one()
        if not self.sudo().approval_workflow_ids:
            return False
        last_approval_workflow = self.sudo().approval_workflow_ids.sorted(
            key=lambda workflow: workflow.create_date, reverse=True
        )[0]
        return last_approval_workflow.decision == 'approved'

    @api.multi
    def action_invoice_cancel(self):
        for rec in self:
            if rec.sudo().approval_workflow_ids:
                rec.sudo().write({'approved': False})
        return super(AccountInvoice, self).action_invoice_cancel()

    @api.multi
    def _set_up_approval_workflow(self):
        self.ensure_one()

        if self.state == 'in_approval' or any(not workflow.decision for workflow in self.approval_workflow_ids):
            raise exceptions.UserError(_('Invoice is already waiting for approval. Can not start a new approval '
                                         'workflow'))

        self.write({'approved': False})

        # Create the actual workflow
        approval_workflow = self.env['invoice.approval.workflow'].create({
            'invoice_id': self.id,
            'decision': False
        })

        # Find active approval steps and copy them as workflow approval steps
        active_approval_steps = self.env['invoice.approval.step'].search([])
        for approval_step in active_approval_steps:
            workflow_step_values = approval_step.copy_data({
                'workflow_id': approval_workflow.id,
                'decision_made': False
            })[0]
            workflow_approval_step = self.env['invoice.approval.workflow.step'].create(workflow_step_values)

            # Match approval conditions to the invoice
            approval_step_conditions = approval_step.mapped('condition_ids').filtered(
                lambda condition: condition.approver_id and condition.approver_id.active and
                                  condition.approver_id.user_id.active
            )
            matched_approval_step_conditions = approval_step_conditions.filtered(
                lambda condition: condition.sudo()._invoice_matches_condition(self)
            )

            # Create workflow step matched approvers and their conditions
            approvers = matched_approval_step_conditions.mapped('approver_id')
            for approver in approvers:
                condition_ids = []

                # Set the delegate as the approver if the approver is currently unavailable and the delegate is set.
                current_approver = approver.check_absences_and_get_available_approver()
                if not current_approver:
                    current_approver = approver

                workflow_step_approver = self.env['invoice.approval.workflow.step.approver'].create({
                    'approver_id': current_approver.id,
                    'original_approver_id': approver.id,
                    'workflow_step_id': workflow_approval_step.id,
                    'matched_condition_ids': [(5,)] + condition_ids
                })

                approver_matched_approval_step_conditions = matched_approval_step_conditions.filtered(
                    lambda condition: condition.approver_id == approver
                )
                for matched_condition in approver_matched_approval_step_conditions:
                    matched_condition_values = matched_condition.copy_data({
                        'workflow_step_id': workflow_approval_step.id,
                        'workflow_approver_id': workflow_step_approver.id,
                        'approver_id': current_approver.id
                    })[0]
                    self.env['inv.approval.workflow.condition'].create(matched_condition_values)

        # Set steps as active
        approval_workflow_steps = approval_workflow.step_ids
        for step in approval_workflow_steps.sorted(key=lambda r: r.sequence):
            matched_approver_ids = step.matched_approver_ids.filtered(
                lambda approver: approver.approver_id.type != 'auditor'
            )
            if matched_approver_ids or step.default_approver:
                step_vals = {'action_needed': True}
                if step.deadline_days or step.deadline_hours:
                    now = datetime.utcnow()
                    deadline = now + relativedelta(days=step.deadline_days or 0, hours=step.deadline_hours or 0)
                    step_vals['deadline'] = deadline
                step.write(step_vals)
                break

        active_approval_steps = approval_workflow.step_ids.filtered(lambda approval_step: approval_step.action_needed)
        active_approval_steps.inform_approvers_about_approval_action()

        self.write({'state': 'in_approval', 'expense_state': 'in_approval'})

        return approval_workflow

    @api.multi
    def _find_current_invoice_approval_workflow_step(self):
        self.ensure_one()
        workflows = self.approval_workflow_ids
        active_workflows = workflows.filtered(lambda workflow: not workflow.decision)
        workflow_steps = active_workflows.mapped('step_ids')
        active_workflow_steps = workflow_steps.filtered(
            lambda workflow_step: not workflow_step.decision_made and workflow_step.action_needed
        ).sorted(key=lambda workflow_step: workflow_step.sequence)
        if not active_workflow_steps:
            return
        return active_workflow_steps[0]

    @api.multi
    def action_invoice_approval_approve(self):
        self.ensure_one()
        workflow_step = self._find_current_invoice_approval_workflow_step()
        if not workflow_step:
            raise exceptions.UserError(_('You can not perform this action because the invoice does not have any '
                                         'active workflow steps that could be approved'))
        workflow_step._set_matched_approver_approval_decision('approved')

    @api.multi
    def action_invoice_approval_disapprove(self):
        self.ensure_one()
        workflow_step = self._find_current_invoice_approval_workflow_step()
        if not workflow_step:
            raise exceptions.UserError(_('You can not perform this action because the invoice does not have any '
                                         'active workflow steps that could be disapproved'))
        return workflow_step._open_invoice_disapproval_wizard()

    @api.multi
    def action_invoice_approval_force_approve(self):
        self.ensure_one()
        workflow_step = self._find_current_invoice_approval_workflow_step()
        if not workflow_step:
            raise exceptions.UserError(_('You can not perform this action because the invoice does not have any '
                                         'active workflow steps that could be approved'))
        workflow_step.workflow_id.action_approve()

    @api.multi
    def action_invoice_approval_force_disapprove(self):
        self.ensure_one()
        workflow_step = self._find_current_invoice_approval_workflow_step()
        if not workflow_step:
            raise exceptions.UserError(_('You can not perform this action because the invoice does not have any '
                                         'active workflow steps that could be disapproved'))
        return workflow_step.workflow_id.action_disapprove()

    @api.multi
    @api.depends('approval_workflow_ids.step_ids', 'approved')
    def _compute_allow_performing_approval_action(self):
        invoice_approval_enabled = self.env.user.sudo().company_id.module_invoice_approval_workflow
        for rec in self:
            if not invoice_approval_enabled:
                rec.allow_performing_approval_action = False
                continue
            if rec.approved or not rec.sudo().approval_workflow_ids or rec.allow_performing_force_approval_action:
                rec.allow_performing_approval_action = False
                continue
            active_workflow_step = rec._find_current_invoice_approval_workflow_step()
            if not active_workflow_step:
                rec.allow_performing_approval_action = False
            elif active_workflow_step.decision_made:
                rec.allow_performing_approval_action = False
            else:
                user = self.env.user
                user_in_approvers_list = user.id in active_workflow_step.mapped('matched_approver_ids.approver_id').filtered(
                    lambda approver: approver.type != 'auditor'
                ).mapped('user_id').ids
                rec.allow_performing_approval_action = user_in_approvers_list

    @api.multi
    @api.depends('approval_workflow_ids.decision', 'approved')
    def _compute_allow_performing_force_approval_action(self):
        invoice_approval_enabled = self.env.user.sudo().company_id.module_invoice_approval_workflow
        for rec in self:
            if not invoice_approval_enabled:
                rec.allow_performing_force_approval_action = False
                continue
            approval_workflows = rec.sudo().approval_workflow_ids
            if rec.approved or not approval_workflows or all(workflow.decision for workflow in approval_workflows):
                rec.allow_performing_force_approval_action = False
            else:
                user = self.env.user
                is_approval_administrator = user.has_group('invoice_approval_workflow.invoice_approval_administrator')
                rec.allow_performing_force_approval_action = is_approval_administrator

    @api.multi
    def ask_again_for_approval(self):
        if not self.env.user.is_premium_manager():
            raise exceptions.UserError(_('Only managers are allowed to ask for approval again'))
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        if invoice_approval_is_active:
            for rec in self.filtered(lambda invoice: invoice.type in ['in_invoice', 'in_refund']):
                rec.action_invoice_cancel()
                rec.action_invoice_draft()
                rec._prepare_invoice_for_approval_workflow('action_invoice_open')

    @api.multi
    def unlink(self):
        if self.env.user.is_accountant():
            # Allow accountants to unlink invoices in approval
            invoices_to_reset_to_draft = self.filtered(lambda invoice: invoice.state == 'in_approval')
            is_system = self.env.user.has_group('base.group_system')
            if not is_system:
                # If the invoice is not unlinked by admin - don't allow invoices that have already been approved once
                # to be unlinked.
                invoices_to_reset_to_draft = invoices_to_reset_to_draft.filtered(
                    lambda invoice: not any(
                        workflow.decision == 'approved' for workflow in invoice.approval_workflow_ids
                    )
                )
            invoices_to_reset_to_draft.write({'state': 'draft'})
        return super(AccountInvoice, self).unlink()

    @api.model
    def create_account_invoice_approve_action(self):
        action = self.env.ref('invoice_approval_workflow.account_invoice_approval_approve')
        if action:
            action.create_action()
