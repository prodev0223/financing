# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models, tools


class ReportInvoiceProcessingIssue(models.TransientModel):
    _name = 'report.invoice.processing.issue'

    @api.multi
    def _get_default_invoice_id(self):
        return self._context.get('active_id', False)

    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra', readonly=1,
                                 default=_get_default_invoice_id)
    message = fields.Text('Klaidos aprašymas')

    @api.multi
    def report_issue(self):
        if not self.env.user.is_accountant():
            raise exceptions.ValidationError(_('Neturite teisių pranešti apie dokumento apdorojimo klaidą'))
        invoice = self.invoice_id
        if not invoice:
            raise exceptions.Warning(_('Nepavyko nustatyti sąskaitos. Perkraukite puslapį'))
        if not invoice.imported_pic:
            raise exceptions.UserError(_('Negalima pranešti apie sąskaitos apdorojimo klaidą, nes sąskaita atėjo ne iš '
                                         'dokumentų apdorojimo'))
        internal = self.env['res.company']._get_odoorpc_object()
        vals = {
            'dbname': self.env.cr.dbname,
            'external_id': invoice.id,
            'document_number': invoice.reference or invoice.number or invoice.proforma_number,
            'comment': self.message or ''
        }
        res = internal.env['database.mapper'].report_mistake(**vals)
        return self.env.ref('robo.report_invoice_processing_issue_done_action').read()[0]
