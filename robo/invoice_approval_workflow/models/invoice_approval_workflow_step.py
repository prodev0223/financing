# -*- coding: utf-8 -*-
import ast
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.l10n_lt_payroll.model.work_norm import CODES_HOLIDAYS, CODES_ABSENCE

from odoo import _, api, exceptions, fields, models, tools


class InvoiceApprovalWorkflowStep(models.Model):
    _name = 'invoice.approval.workflow.step'
    _inherit = ['invoice.approval.step', 'mail.thread']

    workflow_id = fields.Many2one('invoice.approval.workflow', string='Approval workflow', readonly=True,
                                  required=True, ondelete='cascade')
    matched_approver_ids = fields.One2many('invoice.approval.workflow.step.approver', 'workflow_step_id',
                                           string='Workflow step approvers', inverse='_inform_about_waiting_approval')
    number_of_approvers = fields.Integer(string='Number of approvers', compute='_compute_number_of_approvers')
    number_of_approved_approvers = fields.Integer(string='Number of approvers who approved',
                                                  compute='_compute_number_of_approved_approvers')
    decision_made = fields.Selection([('approved', 'Approved'), ('disapproved', 'Disapproved')],
                                     string='Decision made', compute='_compute_decision_made', store=True,
                                     inverse='_prepare_next_approval_step')
    force_decided = fields.Boolean(string='Force decided', related='workflow_id.force_decided', store=True)
    invoice_id = fields.Many2one('account.invoice', string='Account invoice', related='workflow_id.invoice_id',
                                 store=True, ondelete='cascade')
    number_of_approvals_required = fields.Integer(string='Number of approvals required',
                                                  compute='_compute_number_of_approvals_required')
    invoice_number = fields.Char(string='Invoice number', related='invoice_id.computed_number', readonly=True)
    amount_total_signed = fields.Monetary(string='Invoice amount', related='invoice_id.amount_total_signed',
                                          readonly=True)
    amount_total_company_signed = fields.Monetary(string='Invoice amount company currency', readonly=True,
                                                  related='invoice_id.amount_total_company_signed')
    invoice_submitted = fields.Char(string='Invoice submitted by', related='invoice_id.submitted', readonly=True)
    invoice_supplier = fields.Many2one('res.partner', string='Invoice supplier', related='invoice_id.partner_id',
                                       readonly=True)
    invoice_pdf = fields.Binary(string='Invoice pdf', related='invoice_id.pdf', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Invoice Currency', related='invoice_id.currency_id',
                                  readonly=True)
    company_currency_id = fields.Many2one('res.currency', related='invoice_id.company_currency_id', readonly=True)
    allow_performing_approval_action = fields.Boolean(compute='_compute_allow_performing_approval_action')
    action_needed = fields.Boolean(string='Waiting for a decision from approvers')
    condition_number = fields.Integer(string='Number of conditions', compute='_compute_condition_number')
    deadline = fields.Datetime(string='Deadline', readonly=True)
    deadline_reached = fields.Boolean(string='Deadline has been reached', readonly=True)
    deadline_action_executed = fields.Boolean(string='The deadline action has been executed', readonly=True)
    date_invoice = fields.Date(string='Date invoice', related='invoice_id.date_invoice', readonly=True)
    invoice_reference = fields.Char(string='Reference', related='invoice_id.reference', readonly=True)
    invoice_line_ids = fields.Many2many('account.invoice.line', string='Invoice lines',
                                        compute='_compute_invoice_line_ids', readonly=True)
    waiting_for_text = fields.Char('Waiting for', compute='_compute_waiting_for_text', compute_sudo=True)
    related_message_ids = fields.One2many('mail.message', 'res_id', string='Messages',
                                           compute='_compute_related_message_ids', auto_join=True)

    @api.multi
    @api.depends('invoice_id', 'invoice_id.invoice_line_ids')
    def _compute_invoice_line_ids(self):
        for rec in self.filtered(lambda ws: ws.invoice_id):
            rec.invoice_line_ids = [(6, 0, rec.invoice_id.invoice_line_ids.ids)]

    @api.multi
    @api.depends('matched_approver_ids')
    def _compute_number_of_approvers(self):
        for rec in self:
            rec.number_of_approvers = len(
                rec.matched_approver_ids.filtered(lambda approver: approver.approver_id.type != 'auditor')
            )

    @api.multi
    @api.depends('matched_approver_ids.approval_decision')
    def _compute_number_of_approved_approvers(self):
        for rec in self:
            approvers = rec.matched_approver_ids.filtered(lambda approver: approver.approver_id.type != 'auditor')
            approved_approvers = approvers.filtered(lambda approver: approver.approval_decision == 'approved')
            rec.number_of_approved_approvers = len(approved_approvers)

    @api.multi
    @api.depends('matched_approver_ids.approval_decision')
    def _compute_decision_made(self):
        for rec in self:
            approvers = rec.matched_approver_ids.filtered(lambda approver: approver.approver_id.type != 'auditor')
            if any(approver.approval_decision == 'disapproved' for approver in approvers):
                rec.decision_made = 'disapproved'
            else:
                number_of_approvers = rec.number_of_approvers
                approvals_needed = number_of_approvers
                if rec.approval_condition == 'number_of_approvers':
                    approvals_needed = min(number_of_approvers, rec.approvals_needed)
                if rec.number_of_approved_approvers >= approvals_needed:
                    rec.decision_made = 'approved'
                else:
                    rec.decision_made = False

    @api.multi
    @api.depends('approval_condition', 'matched_approver_ids', 'approvals_needed')
    def _compute_number_of_approvals_required(self):
        for rec in self:
            number_of_matched_approvers = len(
                rec.matched_approver_ids.filtered(lambda approver: approver.approver_id.type != 'auditor')
            )
            if number_of_matched_approvers != 0:
                if rec.approval_condition == 'all':
                    rec.number_of_approvals_required = number_of_matched_approvers
                else:
                    rec.number_of_approvals_required = min(rec.approvals_needed, number_of_matched_approvers)
            else:
                if rec.default_approver:
                    rec.number_of_approvals_required = 1
                else:
                    rec.number_of_approvals_required = 0

    @api.multi
    @api.depends('matched_approver_ids.approver_id', 'decision_made')
    def _compute_allow_performing_approval_action(self):
        for rec in self:
            if rec.decision_made:
                rec.allow_performing_approval_action = False
            else:
                user = self.env.user
                matched_approvers = self.sudo().mapped('matched_approver_ids')
                user_in_approvers_list = user.id in matched_approvers.mapped('approver_id').filtered(
                    lambda approver: approver.type != 'auditor'
                ).mapped('user_id').ids
                user_is_default_approver = user.id == rec.default_approver.user_id.id
                if user_in_approvers_list or not matched_approvers and user_is_default_approver:
                    rec.allow_performing_approval_action = True
                else:
                    rec.allow_performing_approval_action = False

    @api.multi
    @api.depends('matched_approver_ids.matched_condition_ids')
    def _compute_condition_number(self):
        for rec in self:
            rec.condition_number = self.env['inv.approval.workflow.condition'].search_count([
                ('workflow_step_id', '=', rec.id)
            ])

    @api.multi
    @api.depends('matched_approver_ids', 'matched_approver_ids.approval_decision', 'decision_made')
    def _compute_waiting_for_text(self):
        number_of_approvers_to_show = 5
        for rec in self:
            if not rec.action_needed:
                rec.waiting_for_text = '-'
                continue

            approvers = rec.matched_approver_ids
            approvers_waiting_for = approvers.sudo().filtered(lambda approver: not approver.approval_decision).mapped('approver_id')
            if not approvers_waiting_for:
                approvers_waiting_for = rec.sudo().default_approver

            if not approvers_waiting_for:
                rec.waiting_for_text = '-'
                continue

            approver_users = approvers_waiting_for.mapped('user_id')
            user_names = approver_users.mapped('name')
            waiting_for_text = ', '.join(user_names[:number_of_approvers_to_show])
            number_of_other_users = max(len(user_names) - number_of_approvers_to_show, 0)
            if number_of_other_users > 0:
                waiting_for_text += _(' +{} others').format(number_of_other_users)
            rec.waiting_for_text = waiting_for_text

    @api.multi
    def _compute_related_message_ids(self):
        """
        Finds the related messages - messages from this approval workflow step and the messages from the related invoice
        """
        for rec in self:
            rec.related_message_ids = self.env['mail.message'].sudo().search([
                '|',
                '&',
                ('res_id', '=', rec.id),
                ('model', '=', self._name),
                '&',
                ('res_id', '=', rec.invoice_id.id),
                ('model', '=', 'account.invoice')
            ])

    @api.multi
    @api.constrains('matched_approver_ids')
    def _check_matched_approver_ids_dont_repeat(self):
        for rec in self:
            record_approvers = rec.matched_approver_ids
            for record_approver in record_approvers:
                approver_recs = record_approvers.filtered(
                    lambda approver: approver.approver_id.id == record_approver.approver_id.id
                )
                if len(approver_recs) > 1:
                    raise exceptions.UserError(_('An approver can only be assigned to an approval step once.'))

    @api.multi
    def _ensure_user_can_perform_approval_action(self):
        self.ensure_one()
        user = self.env.user
        user_in_approvers_list = user.id in self.sudo().mapped('matched_approver_ids.approver_id').filtered(
            lambda approver: approver.type != 'auditor'
        ).mapped('user_id').ids
        if not user_in_approvers_list:
            raise exceptions.UserError(_('You can not perform this approval action because you are not in the approver '
                                         'list'))

    @api.multi
    def _set_matched_approver_approval_decision(self, approval_decision, reason=None):
        user = self.env.user
        for rec in self:
            if rec.decision_made:
                raise exceptions.UserError(_('You can not perform this action since a decision has already been made.'))
            rec._ensure_user_can_perform_approval_action()
            matched_approver = rec.matched_approver_ids.sudo().filtered(
                lambda approver: approver.approver_id.user_id.id == user.id
            )
            if matched_approver:
                matched_approver = matched_approver[0]
                matched_approver.sudo().write({'approval_decision': approval_decision})
                rec._leave_decision_comment(matched_approver, approval_decision, reason)
                if rec.decision_made == 'approved':
                    rec._prepare_next_approval_step()

            if approval_decision == 'disapproved':
                rec.sudo().write({'action_needed': False})

        self.mapped('workflow_id')._update_invoice_after_decision()

    @api.multi
    def _inform_about_waiting_approval(self):
        approvers = self.mapped('matched_approver_ids')
        approvers = approvers.filtered(lambda approver: approver.workflow_step_id.action_needed and
                                                        not approver.informed)
        approvers.inform_about_approval_action_waiting()

    @api.multi
    def action_approve(self):
        self._set_matched_approver_approval_decision('approved')

    @api.multi
    def action_disapprove(self):
        self.ensure_one()
        return self._open_invoice_disapproval_wizard()

    @api.multi
    def action_open_matched_conditions(self):
        self.ensure_one()
        action = self.env.ref('invoice_approval_workflow.inv_approval_workflow_condition_action')
        action = action.read()[0]
        domain = action.get('domain') or list()
        domain.append(('workflow_step_id', '=', self.id))
        action['domain'] = domain
        return action

    @api.multi
    def _open_invoice_disapproval_wizard(self):
        self.ensure_one()
        action = self.env.ref('invoice_approval_workflow.disapprove_account_invoice_action')
        action = action.read()[0]
        context = ast.literal_eval(action['context'])
        context['active_id'] = self.id
        action['context'] = context
        return action

    @api.multi
    def inform_approvers_about_approval_action(self):
        for rec in self:
            matched_approver_ids = rec.mapped('matched_approver_ids')
            if not matched_approver_ids:
                default_approver = rec.default_approver
                if default_approver:
                    matched_default_approver = self.env['invoice.approval.workflow.step.approver'].sudo().create({
                        'approver_id': default_approver.id,
                        'workflow_step_id': rec.id
                    })
                    matched_approver_ids = matched_default_approver
            matched_approver_ids.inform_about_approval_action_waiting()

    @api.multi
    def _prepare_next_approval_step(self):
        steps_already_prepared = self.env['invoice.approval.workflow.step']
        for step in self:
            if step in steps_already_prepared or step.decision_made != 'approved':
                continue
            step.write({'action_needed': False})
            workflow = step.workflow_id
            further_workflow_steps = workflow.sudo().step_ids.filtered(
                lambda s: s.sequence > step.sequence
            )
            for further_step in further_workflow_steps:
                if step in steps_already_prepared:
                    continue
                steps_already_prepared |= further_step

                further_step_matched_approver_ids = further_step.matched_approver_ids
                if further_step_matched_approver_ids:
                    further_step.write({'action_needed': True})
                    self.sudo().reconfigure_approvers_based_on_holidays(further_step, inform_new_approvers=False)
                    further_step.inform_approvers_about_approval_action()

                    if further_step.deadline_days or further_step.deadline_hours:
                        now = datetime.utcnow()
                        deadline = now + relativedelta(
                            days=further_step.deadline_days or 0,
                            hours=further_step.deadline_hours or 0
                        )
                        further_step.write({'deadline': deadline})

                    break

    @api.multi
    def _leave_decision_comment(self, approver, decision, reason=None):
        self.ensure_one()
        if not decision:
            raise exceptions.UserError(_('Can not leave a decision comment if no decision has been made'))

        body = _('{} has {} this invoice.').format(
            approver.approver_id.user_id.name,
            _('approved') if decision == 'approved' else _('disapproved')
        )

        if decision != 'approved':
            if not reason:
                raise exceptions.UserError(_('Can not leave a decision comment with out the decision reason if the '
                                             'decision is not for the approval of the workflow step'))
            body += _(' Reason: {}').format(reason)

        self._leave_comment(body)

    @api.multi
    def _leave_comment(self, comment):
        self.ensure_one()
        msg = {
            'body': comment,
            'front_message': True,
            'rec_model': 'invoice.approval.workflow.step',
            'rec_id': self.id,
            'subtype': 'robo.mt_robo_front_message'
        }
        self.robo_message_post(**msg)

    @api.multi
    @api.returns('self', lambda value: value.id)
    def robo_message_post(self, **kwargs):
        """
        Overridden method posts message the workflow which in turn posts message on all of the workflow steps.
        """
        is_comment = kwargs.get('message_type') == 'notification' and kwargs.get('subtype') == 'mail.mt_note'
        user = self.env.user
        user_is_approver = user.id in self.mapped('matched_approver_ids.approver_id.user_id').ids
        user_is_approval_administrator = user.has_group('invoice_approval_workflow.invoice_approval_administrator')
        allow_posting_on_workflow = user_is_approver or user_is_approval_administrator

        if self._context.get('prevent_recursion') or not is_comment or not allow_posting_on_workflow:
            return super(InvoiceApprovalWorkflowStep, self).robo_message_post(**kwargs)

        # Post with sudo
        kwargs['author_id'] = self.env.user.partner_id.id
        kwargs['force_front_message'] = True
        return self.workflow_id.sudo().robo_message_post(**kwargs)

    @api.model
    def reconfigure_approvers_based_on_holidays(self, approval_steps=None, inform_new_approvers=True):
        # Find approval steps to reconfigure
        if not approval_steps:
            approval_steps = self.search([('decision_made', '=', False), ('action_needed', '=', True)])
        else:
            approval_steps = approval_steps.filtered(lambda step: not step.decision_made and step.action_needed)

        # Find all approvers who have not made a decision yet
        matched_approvers = approval_steps.mapped('matched_approver_ids').filtered(lambda a: not a.approval_decision)

        # Find related employee records
        related_employee_records = matched_approvers.mapped('approver_id.user_id.employee_ids')
        related_employee_records |= matched_approvers.mapped('original_approver_id.user_id.employee_ids')

        # Find holidays for the matched approvers
        today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        holiday_codes = CODES_HOLIDAYS + CODES_ABSENCE
        holidays = self.env['hr.holidays'].search([
            ('type', '=', 'remove'),
            ('employee_id', 'in', related_employee_records.ids),
            ('date_from_date_format', '<=', today),
            ('date_to_date_format', '>=', today),
            ('holiday_status_id.tabelio_zymejimas_id.code', 'in', holiday_codes),
            ('state', '=', 'validate'),
        ])

        approvers_to_inform = self.env['invoice.approval.workflow.step.approver']

        for matched_approver in matched_approvers:
            original_approver = matched_approver.original_approver_id
            current_approver = matched_approver.approver_id
            original_approver_employees = original_approver.user_id.employee_ids
            current_approver_employees = current_approver.user_id.employee_ids
            original_approver_is_on_holidays = holidays.filtered(lambda h: h.employee_id in original_approver_employees)
            current_approver_is_on_holidays = holidays.filtered(lambda h: h.employee_id in current_approver_employees)
            new_approver_is_set = matched_approver.approver_id != matched_approver.original_approver_id
            inform_matched_approver = False
            current_approver_is_no_longer_the_delegate = current_approver != original_approver.delegate_id
            if original_approver and \
                    (not original_approver_is_on_holidays or current_approver_is_no_longer_the_delegate) and \
                    new_approver_is_set:
                # Original approver is no longer on holiday
                matched_approver.write({'approver_id': original_approver.id, 'informed': False})
                inform_matched_approver = inform_new_approvers
            elif current_approver_is_on_holidays:
                # Find another approver who could make a decision
                available_approver = current_approver.check_absences_and_get_available_approver()
                if current_approver != available_approver:
                    vals = {'approver_id': available_approver.id, 'informed': False}
                    if not original_approver:
                        vals['original_approver_id'] = current_approver.id
                    matched_approver.write(vals)
                    inform_matched_approver = inform_new_approvers
            if inform_matched_approver:
                approvers_to_inform |= matched_approver

        approvers_to_inform.inform_about_approval_action_waiting()

    @api.model
    def create_workflow_step_approve_action(self):
        action = self.env.ref('invoice_approval_workflow.invoice_approval_workflow_step_approve')
        if action:
            action.create_action()

    @api.multi
    def _normalise_sequences(self):
        # Sequence should never be normalised for workflow step. Field is inherited from approval step where this
        # normalisation is needed.
        return
