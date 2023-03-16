# -*- coding: utf-8 -*-

from odoo import api, fields, models


class InvoiceAnalyticWizardLine(models.TransientModel):
    _inherit = 'invoice.analytic.wizard.line'

    any_invoice_in_approval = fields.Boolean(compute='_compute_any_invoice_in_approval')

    @api.multi
    @api.depends('invoice_line_id.invoice_id')
    def _compute_any_invoice_in_approval(self):
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        for rec in self:
            if not invoice_approval_is_active:
                rec.any_invoice_in_approval = False
            else:
                invoices = rec.mapped('invoice_line_id.invoice_id')
                rec.any_invoice_in_approval = any(invoice.expense_state == 'in_approval' for invoice in invoices)

    @api.multi
    def change_analytics_while_in_approval(self):
        self.ensure_one()
        self.check_invoice_approval_state_and_call_method(self.change_analytics)

    @api.multi
    def split_invoice_line_while_in_approval(self):
        self.ensure_one()
        self.check_invoice_approval_state_and_call_method(self.split_invoice_line)

    @api.multi
    def check_invoice_approval_state_and_call_method(self, method_to_call):
        self.ensure_one()

        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow

        invoice = self.invoice_line_id.invoice_id
        if not invoice_approval_is_active or not invoice or invoice.expense_state != 'in_approval':
            return method_to_call()

        workflow = invoice.invoice_approval_workflow.filtered(lambda r: not r.decision)
        invoice.action_invoice_cancel()
        invoice.action_invoice_draft()
        workflow.with_context(do_not_leave_a_decision_comment=True).sudo().write({
            'force_decided': True,
            'decision': 'disapproved'
        })
        workflow_steps = workflow.sudo().mapped('step_ids')
        workflow_steps.write({'action_needed': False})
        workflow_steps.filtered(lambda step: not step.decision_made).write({'decision_made': 'disapproved'})
        callback = workflow.method_to_execute_on_approval if workflow else False

        res = method_to_call()

        if invoice.state != 'in_approval':  # State might be changed by calling invoice open in the method_to_call part
            invoice.sudo()._prepare_invoice_for_approval_workflow(callback=callback)

        return res


InvoiceAnalyticWizardLine()
