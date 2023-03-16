# -*- coding: utf-8 -*-

from odoo import api, fields, models


class InvoiceAnalyticWizardAll(models.TransientModel):
    _inherit = 'invoice.analytic.wizard.all'

    any_invoice_in_approval = fields.Boolean(compute='_compute_any_invoice_in_approval')

    @api.multi
    @api.depends('invoice_id', 'invoice_ids')
    def _compute_any_invoice_in_approval(self):
        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow
        for rec in self:
            if not invoice_approval_is_active:
                rec.any_invoice_in_approval = False
            else:
                invoices = rec.invoice_id if rec.invoice_id else rec.invoice_ids
                rec.any_invoice_in_approval = any(invoice.expense_state == 'in_approval' for invoice in invoices)

    @api.multi
    def change_analytics_while_in_approval(self):
        invoices = self.invoice_id if self.invoice_id else self.invoice_ids

        invoice_approval_is_active = self.env.user.sudo().company_id.module_invoice_approval_workflow

        invoice_callbacks = {}

        if invoice_approval_is_active:
            invoices = invoices.filtered(lambda invoice: invoice.expense_state == 'in_approval')
            for invoice in invoices:
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
                invoice_callbacks[invoice.id] = callback

        res = super(InvoiceAnalyticWizardAll, self).change_analytics()

        if invoice_approval_is_active:
            for invoice in invoices:
                invoice.sudo()._prepare_invoice_for_approval_workflow(callback=invoice_callbacks.get(invoice.id))

        return res


InvoiceAnalyticWizardAll()
