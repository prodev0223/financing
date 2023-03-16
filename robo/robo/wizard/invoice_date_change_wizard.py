# -*- coding: utf-8 -*-
from odoo import fields, models, api


class InvoiceDateChangeWizard(models.TransientModel):

    _name = 'invoice.date.change.wizard'
    _description = '''Wizard that is used to change invoice date 
    and due date without manually cancelling the record'''

    invoice_id = fields.Many2one('account.invoice', string='Related invoice', inverse='_set_invoice_id')

    current_date_invoice = fields.Date(
        string='Current date invoice',
        compute='_compute_current_invoice_dates',
    )
    current_date_due = fields.Date(
        string='Current date due',
        compute='_compute_current_invoice_dates',
    )
    current_date_issued = fields.Date(
        string='Current date issued',
        compute='_compute_current_invoice_dates',
    )
    current_registration_date = fields.Date(
        string='Current registration date',
        compute='_compute_current_invoice_dates',
    )
    supplier_invoice = fields.Boolean(compute='_compute_supplier_invoice')

    date_invoice = fields.Date(string='Date invoice')
    date_due = fields.Date(string='Date due')
    date_issued = fields.Date(string='Date issued')
    registration_date = fields.Date(string='Registration date')

    @api.multi
    @api.depends('invoice_id', 'invoice_id.type')
    def _compute_supplier_invoice(self):
        """Check whether current invoice is supplier invoice"""
        for rec in self:
            rec.supplier_invoice = rec.invoice_id.type in ['in_invoice', 'in_refund']

    @api.multi
    @api.depends(
        'invoice_id.date_invoice', 'invoice_id.date_due',
        'invoice_id.operacijos_data', 'invoice_id.registration_date',
    )
    def _compute_current_invoice_dates(self):
        """Computes current invoice dates for display"""
        for rec in self:
            rec.current_date_due = rec.invoice_id.date_due
            rec.current_date_invoice = rec.invoice_id.date_invoice
            rec.current_date_issued = rec.invoice_id.operacijos_data
            rec.current_registration_date = rec.invoice_id.registration_date

    @api.multi
    def _set_invoice_id(self):
        """Set default dates based on the invoice"""
        for rec in self:
            rec.write({
                'date_due': rec.invoice_id.date_due,
                'date_invoice': rec.invoice_id.date_invoice,
                'date_issued': rec.invoice_id.operacijos_data,
                'registration_date': rec.invoice_id.registration_date,
            })

    @api.multi
    def change_invoice_dates(self):
        """
        Changes dates for current invoice and related account move.
        If date_invoice is changed, invoice is firstly canceled
        :return: JS action (dict)
        """
        self.ensure_one()

        invoice = self.invoice_id
        values_to_write = {}
        # Collect changed values
        if invoice.date_invoice != self.date_invoice:
            values_to_write['date_invoice'] = self.date_invoice
        if invoice.date_due != self.date_due:
            values_to_write['date_due'] = self.date_due
            values_to_write['date_due_report'] = self.date_due
        if invoice.operacijos_data != self.date_issued:
            values_to_write['operacijos_data'] = self.date_issued
        if invoice.registration_date != self.registration_date:
            values_to_write['registration_date'] = self.registration_date

        # Cancel the invoice if date_invoice is in the values
        if invoice.state in ['paid', 'open'] and 'date_invoice' in values_to_write.keys():
            res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
            invoice.write(values_to_write)
            invoice.with_context(skip_attachments=True).action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False)
        # If it's ONLY date due or invoice is not open/paid values are written directly
        elif values_to_write:
            invoice.write(values_to_write)
            invoice.move_id.line_ids.write({'date_maturity': self.date_due})
        # Close the wizard and reload the view
        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}
