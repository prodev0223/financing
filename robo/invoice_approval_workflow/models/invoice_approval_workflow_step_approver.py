# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class InvoiceApprovalWorkflowStepApprover(models.Model):
    _name = 'invoice.approval.workflow.step.approver'
    _inherit = ['mail.thread']

    approver_id = fields.Many2one('invoice.approver', string='Approver', required=True, ondelete='restrict')
    original_approver_id = fields.Many2one('invoice.approver', string='Original Approver',
                                           default=lambda self: self.approver_id)
    matched_condition_ids = fields.One2many('inv.approval.workflow.condition', 'workflow_approver_id',
                                            string='Matched conditions',
                                            help='Conditions that were matched for this approver at this step')
    workflow_step_id = fields.Many2one('invoice.approval.workflow.step', string='Approval step', ondelete='cascade',
                                       required=True)
    approval_decision = fields.Selection([('approved', 'Approved'), ('disapproved', 'Disapproved')],
                                         string='Decision made')
    approver_type = fields.Selection([('approver', 'Approver'), ('auditor', 'Auditor')], string='Approver type',
                                     related='approver_id.type')
    informed = fields.Boolean('User has been informed about the waiting approval', readonly=True)

    @api.multi
    def name_get(self):
        return [(rec.id, rec.approver_id.user_id.name) for rec in self]

    @api.multi
    def inform_about_approval_action_waiting(self):
        workflow_steps = self.mapped('workflow_step_id')
        for workflow_step in workflow_steps:
            invoice = workflow_step.sudo().invoice_id
            body = _('A new invoice {} is waiting for your approval for invoice approval step {}').format(
                invoice.reference or invoice.number or invoice.proforma_number,
                workflow_step.name
            )
            step_approvers = self.filtered(lambda approver: approver.workflow_step_id == workflow_step and
                                                            not approver.informed)
            subject = _('New invoice is waiting for approval')
            msg = {
                'body': body,
                'subject': subject,
                'priority': 'medium',
                'front_message': True,
                'rec_model': 'invoice.approval.workflow.step',
                'rec_id': workflow_step.id,
                'view_id': self.env.ref(
                    'invoice_approval_workflow.invoice_approval_workflow_step_front_end_view_form').id
            }

            email_body = None
            if any(step_approver.approver_id.notification_type == 'system_and_email' for step_approver in step_approvers):
                url = 'https://{}.robolabs.lt/web?#id={}&view_type=form&view_id={}&robo_menu_id={}&' \
                      'model=invoice.approval.workflow.step&menu_id={}&action={}'.format(
                    self.env.cr.dbname,
                    workflow_step.id,
                    self.env.ref('invoice_approval_workflow.invoice_approval_workflow_step_front_end_view_form').id,
                    self.env.ref('invoice_approval_workflow.invoice_approval_front_end_menu_container').id,
                    self.env.ref('invoice_approval_workflow.invoice_approval_workflow_review_action').id,
                    self.env.ref('invoice_approval_workflow.invoice_approval_workflow_step_front_end_action').id,
                )
                email_body = body
                email_body += '''
                <br/>
                <table style="border: 1px solid black; border-collapse: collapse; font-size: 12px;">
                    <tr style="font-weight: bold;">
                        <td style="border: 1px solid black; padding: 2px; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; font-weight: bold;">{}</td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                    </tr>
                </table>
                <br/>
                '''.format(
                    _('Supplier'),
                    _('Date'),
                    _('Reference'),
                    _('Amount'),
                    invoice.partner_id.name,
                    invoice.date_invoice,
                    invoice.reference,
                    invoice.amount_total_signed,
                )
                invoice_lines_html = ''
                for invoice_line in invoice.invoice_line_ids:
                    invoice_lines_html += '''
                    <tr>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; word-break: keep-all; padding: 2px; white-space: nowrap;">{}</td>
                        <td style="border: 1px solid black; word-break: keep-all; padding: 2px; white-space: nowrap;">{}</td>
                        <td style="border: 1px solid black; word-break: keep-all; padding: 2px; white-space: nowrap;">{}</td>
                        <td style="border: 1px solid black; padding: 2px;">{}</td>
                        <td style="border: 1px solid black; word-break: keep-all; padding: 2px; white-space: nowrap;">{}</td>
                        <td style="border: 1px solid black; word-break: keep-all; padding: 2px; white-space: nowrap;">{}</td>
                    </tr>
                    '''.format(
                        invoice_line.name,
                        invoice_line.account_id.name or '-',
                        invoice_line.account_analytic_id.name or '-',
                        invoice_line.quantity,
                        invoice_line.price_unit,
                        invoice_line.discount,
                        ', '.join(invoice_line.invoice_line_tax_ids.mapped('name')) if invoice_line.invoice_line_tax_ids else '-',
                        invoice_line.price_subtotal,
                        invoice_line.total_with_tax_amount,
                    )

                invoice_line_table = '''
                <table style="border: 1px solid black; font-size: 11px; border-collapse: collapse">
                    <tr>
                        <td style="border: 1px solid black; padding: 2px; word-break: break-word; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: break-word; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: break-word; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                        <td style="border: 1px solid black; padding: 2px; word-break: keep-all; font-weight: bold;">{}</td>
                    </tr>
                    {}
                </table>
                '''.format(
                    _('Name'), _('Account'), _('Analytic account'), _('Quantity'), _('Price unit'), _('Discount'),
                    _('Taxes'), _('Total'), _('Total (with tax)'), invoice_lines_html
                )
                email_body += invoice_line_table
                email_body += _('''
                <br/><br/><a href=\"{}\" style=\"padding: 8px 12px; font-size: 12px; color: #FFFFFF; \
                text-decoration: none !important; font-weight: 400; background-color: #3498DB; 
                border: 0px solid #3498DB; border-radius:3px; margin-top: 10px;\">Open</a>
                ''').format(url)

            users_sent_to = self.env['res.users']

            email_notification_mail_channel = self.env.ref(
                'invoice_approval_workflow.approval_notification_mail_channel', False
            )
            partners_allowed_to_be_email_notified = self.env['res.partner']
            if email_notification_mail_channel:
                partners_allowed_to_be_email_notified = email_notification_mail_channel.sudo().channel_partner_ids

            for step_approver in step_approvers:
                msg.update({'partner_ids': step_approver.mapped('approver_id.user_id.partner_id').ids})
                step_approver.with_context(force_do_not_notify=True).robo_message_post(**msg)

                if step_approver.approver_id.notification_type == 'system_and_email' and email_body:
                    user = step_approver.approver_id.user_id
                    if user in users_sent_to:
                        continue
                    user_partner_allowed_to_be_notified = user.partner_id in partners_allowed_to_be_email_notified
                    if email_notification_mail_channel and not user_partner_allowed_to_be_notified:
                        continue
                    users_sent_to |= user
                    self.env['script'].send_email(emails_to=[user.email], subject=subject, body=email_body)

            step_approvers.sudo().write({'informed': True})


InvoiceApprovalWorkflowStepApprover()
