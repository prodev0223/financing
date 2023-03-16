# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, api, tools, _, exceptions, fields


class EDocument(models.Model):
    _inherit = 'e.document'

    overtime_issues = fields.Text(compute='_compute_overtime_issues', store=True)

    @api.multi
    @api.depends('template_id', 'e_document_time_line_ids', 'employee_id2')
    def _compute_overtime_issues(self):
        template = self.env.ref('e_document.overtime_order_template', False)
        for rec in self:
            if not template or rec.template_id != template:
                rec.overtime_issues = None
                continue
            overtime_lines = rec.e_document_time_line_ids
            overtime_times = {date: [
                    (l.time_from, l.time_to) for l in overtime_lines.filtered(lambda l: l.date == date)
                ] for date in overtime_lines.mapped('date')
            }
            overtime_issues = self.env['hr.employee.overtime'].sudo()._get_overtime_issues(
                rec.employee_id2, overtime_times
            )
            if overtime_issues:
                rec.overtime_issues = '\n'.join(overtime_issues)
            else:
                rec.overtime_issues = None

    @api.multi
    def overtime_order_workflow(self):
        self.ensure_one()
        overtime_record = self.env['hr.employee.overtime'].create({
            'employee_id': self.employee_id2.id,
            'overtime_compensation': self.overtime_compensation,
            'overtime_time_line_ids': [(0, 0, line.read()[0]) for line in self.e_document_time_line_ids]
        })
        overtime_record.action_confirm()
        self.write({
            'record_model': 'hr.employee.overtime',
            'record_id': overtime_record.id,
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref('e_document.overtime_order_template', False)
        cancelled_document = self.cancel_id
        if cancelled_document and cancelled_document.template_id == template:
            overtime_records = self.cancel_id.find_related_records()
            if not overtime_records:
                self.raise_no_related_records_found_error()
            else:
                overtime_records.action_draft()
                overtime_records.unlink()
            return True
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self:
            res += rec.check_overtime_order_constraints()
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda rec: not rec.sudo().skip_constraints_confirm):
            issues = rec.check_overtime_order_constraints()
            if issues:
                raise exceptions.ValidationError(issues)
            if rec.overtime_issues and rec.overtime_issues != '':
                raise exceptions.ValidationError(
                    _('Can not form the document since there are issues with the overtime times. If you think this '
                      'is a mistake or you insist on signing this document - please leave a message to your accountant '
                      'at the bottom of this document.')
                )
        return res

    @api.multi
    def check_overtime_order_constraints(self):
        self.ensure_one()
        template = self.env.ref('e_document.overtime_order_template', False)
        if template and self.template_id == template:
            if not self.overtime_request_type:
                return _('Overtime type not specified')
            if not self.overtime_compensation:
                return _('Overtime compensation not specified')
            if not self.e_document_time_line_ids:
                return _('Overtime times not specified')
        return str()


EDocument()
