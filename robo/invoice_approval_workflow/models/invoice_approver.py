# -*- coding: utf-8 -*-
import ast

from odoo import _, api, exceptions, fields, models


class InvoiceApprover(models.Model):
    _name = 'invoice.approver'

    _sql_constraints = [
        (
            'single_user',
            'unique (user_id)',
            _('User is already in the approver list!')
        ),
    ]

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade',
                              domain=lambda self: [
                                  ('groups_id', 'not in', [self.env.ref('base.group_system').id,
                                                           self.env.ref('robo_basic.group_robo_premium_accountant').id])
                              ])
    approval_condition_ids = fields.One2many('invoice.approval.condition', 'approver_id', string='Approval conditions')
    active = fields.Boolean('Active', default=True, inverse='set_user_groups')
    type = fields.Selection(
        [('approver', 'Approver'), ('auditor', 'Auditor')],
        string='Approver type',
        required=True,
        default='approver',
        inverse='set_user_groups'
    )
    condition_number = fields.Integer(string='Number of conditions', compute='_compute_condition_number')
    delegate_id = fields.Many2one('invoice.approver', string='Delegate',
                                  help='User who should approve invoices if this approver is not available',
                                  domain=lambda self: [('user_id.id', '!=', self.user_id.id)],
                                  inverse='_update_currently_waiting_approvals_to_be_approved_by_delegate')
    currently_unavailable = fields.Boolean(string='Approver is currently unavailable',
                                           help='When set the matched invoices will be assigned to the delegated '
                                                'approver',
                                           inverse='_update_currently_waiting_approvals_to_be_approved_by_delegate')
    notification_type = fields.Selection(
        [('system_only', 'System notification'), ('system_and_email', 'System and e-mail notification')],
        string='Approval notifications', required=True, default='system_only',
        inverse='_set_mail_channel_subscription_on_notification_type_change'
    )

    @api.multi
    def _update_currently_waiting_approvals_to_be_approved_by_delegate(self):
        workflow_step_obj = self.env['invoice.approval.workflow.step']
        affected_workflow_steps = workflow_step_obj.sudo().search([
            ('matched_approver_ids.original_approver_id', 'in', self.ids)
        ])
        workflow_step_obj.sudo().reconfigure_approvers_based_on_holidays(affected_workflow_steps, True)

    @api.multi
    @api.constrains('delegate_id')
    def _check_delegate_id_is_not_approver(self):
        for rec in self:
            if rec.delegate_id.user_id == rec.user_id:
                raise exceptions.ValidationError(_('The delegated user can not be the approver user'))

    @api.multi
    def name_get(self):
        return [(rec.id, rec.user_id.name) for rec in self]

    @api.multi
    def _reset_user_group(self):
        # Remove access groups from users when removing them from invoice approvers
        self.mapped('user_id').sudo().write({
            'groups_id': [
                (3, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_approver').id,),
                (3, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_auditor').id,),
                (3, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_enabled_group').id,),
            ]
        })

    @api.multi
    def _set_mail_channel_subscription_on_notification_type_change(self):
        """
        Subscribes and/or unsubscribes approvers to the email notification mail channel depending on the notification
        type preference.
        """
        self.filtered(lambda approver: approver.notification_type == 'system_only').set_mail_channel_subscription(
            action='unsubscribe'
        )
        self.filtered(lambda approver: approver.notification_type == 'system_and_email').set_mail_channel_subscription(
            action='subscribe'
        )

    @api.multi
    def set_mail_channel_subscription(self, action='subscribe'):
        """
        Adds or removes users to/from invoice approval email notification mail channel.
        """
        # Get mail channel
        mail_channel = self.env.ref('invoice_approval_workflow.approval_notification_mail_channel', False)
        if not mail_channel:
            return

        # Get partners
        partners = self.mapped('user_id.partner_id')
        if not partners:
            return

        action = 4 if action == 'subscribe' else 3  # Determine operation type
        data = [(action, partner.id) for partner in partners]  # Format data
        mail_channel.sudo().write({'channel_partner_ids': data})  # Write to mail channel partners

    @api.multi
    def unlink(self):
        user_is_already_a_workflow_step_aprover = self.env['invoice.approval.workflow.step.approver'].search_count([
            ('approver_id', 'in', self.ids)
        ])
        if user_is_already_a_workflow_step_aprover:
            raise exceptions.UserError(_('You can not unlink this approver because this user is already an approver on '
                                         'some invoices. If you wish for this user not to be able to approve invoices '
                                         '- archive the approver.'))
        self._reset_user_group()
        self.set_mail_channel_subscription(action='unsubscribe')
        return super(InvoiceApprover, self).unlink()

    @api.multi
    def write(self, vals):
        if 'user_id' in vals:
            self._reset_user_group()
            res = super(InvoiceApprover, self).write(vals)
            self.set_user_groups()
        else:
            res = super(InvoiceApprover, self).write(vals)
        return res

    @api.multi
    def set_user_groups(self):
        """
        Set the user group as invoice approval approver or invoice approval auditor when changing the type of the
        approver
        """
        self._reset_user_group()
        for rec in self:
            if rec.type == 'approver':
                rec.user_id.write({
                    'groups_id': [(4, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_approver').id,)]
                })
            elif rec.type == 'auditor':
                rec.user_id.write({
                    'groups_id': [(4, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_auditor').id,)]
                })

            if self.env.user.company_id.module_invoice_approval_workflow:
                rec.user_id.write({
                    'groups_id': [
                        (4, self.sudo().env.ref('invoice_approval_workflow.invoice_approval_enabled_group').id,)]
                })

    @api.multi
    def toggle_active(self):
        """ Inverse the value of the field ``active`` on the records in ``self``. """
        for record in self:
            record.active = not record.active

    @api.multi
    @api.depends('approval_condition_ids')
    def _compute_condition_number(self):
        for rec in self:
            rec.condition_number = len(rec.approval_condition_ids)

    @api.multi
    def action_open_approver_approval_conditions(self):
        self.ensure_one()
        action = self.env.ref('invoice_approval_workflow.invoice_approval_condition_action')
        action = action.read()[0]
        domain = action.get('domain') or list()
        domain.append(('approver_id', 'in', self.ids))
        action['domain'] = domain
        context = ast.literal_eval(action['context'])
        context.update({'active_approver_id': self.id})
        action['context'] = context
        return action

    @api.multi
    def check_absences_and_get_available_approver(self, original_approver=None):
        """
        Checks if the approver is absent and if so recursively checks delegates until a delegate who can approve the
        invoice is found
        Returns:
            invoice.approver: Approver who should approve the invoice
        """
        self.ensure_one()

        if not original_approver:
            original_approver = self

        approver_employee_records = self.user_id.employee_ids
        any_employee_is_absent = any(employee.sudo().is_absent for employee in approver_employee_records)
        if any_employee_is_absent:
            potential_delegate = self.delegate_id
            if not potential_delegate or original_approver == potential_delegate:
                # If there's not delegate set for the approver of if the original approver we're looking a delegate for
                # is the next potential delegate (we've come full circle) then return the original approver
                return original_approver

            # Recursive call to find a suitable delegate (someone who's not on holidays)
            delegate = potential_delegate.check_absences_and_get_available_approver(original_approver)
            return delegate
        else:
            return self


InvoiceApprover()
