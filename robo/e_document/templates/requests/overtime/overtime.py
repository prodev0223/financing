# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, api, tools, _, exceptions, fields


class EDocument(models.Model):
    _inherit = 'e.document'

    overtime_request_type = fields.Selection([
            ('overtime', 'Dirbti viršvalandžius'),
            ('holidays', 'Dirbti švenčių dienomis'),
            ('both', 'Dirbti viršvalandžius ir švenčių dienomis')
        ], string='Prašymo tipas', inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]},
        store=True, compute='_compute_overtime_request_type')
    overtime_compensation = fields.Selection([
        ('monetary', 'Mokama už dirbtą laiką'),
        ('holidays', 'Dirbtas laikas atitinkamai padauginamas ir pridedamas prie kasmetinių atostogų trukmės'),
    ], string='Kompensacija', inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})

    @api.multi
    @api.depends('template_id', 'e_document_time_line_ids')
    def _compute_overtime_request_type(self):
        overtime_request_template = self.env.ref('e_document.overtime_request_template', False)
        overtime_order_template = self.env.ref('e_document.overtime_order_template', False)
        for rec in self:
            if not overtime_request_template or rec.template_id not in \
                    [overtime_request_template, overtime_order_template]:
                rec.overtime_request_type = False
                continue
            requested_overtime_days = rec.e_document_time_line_ids
            any_day_is_holiday = any(day.date_is_holiday for day in requested_overtime_days)
            any_day_is_not_holiday = any(not day.date_is_holiday for day in requested_overtime_days)
            if any_day_is_holiday and any_day_is_not_holiday:
                rec.overtime_request_type = 'both'
            elif any_day_is_holiday:
                rec.overtime_request_type = 'holidays'
            else:
                rec.overtime_request_type = 'overtime'

    @api.multi
    def overtime_request_workflow(self):
        self.ensure_one()
        overtime_order_template = self.env.ref('e_document.overtime_order_template')
        generated_id = self.env['e.document'].create({
            'template_id': overtime_order_template.id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'overtime_request_type': self.overtime_request_type,
            'overtime_compensation': self.overtime_compensation,
            'e_document_time_line_ids': [(0, 0, line.read()[0]) for line in self.e_document_time_line_ids],
            'selection_bool_2': 'true'  # Mark that the document comes from a request
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self:
            res += rec.check_overtime_request_constraints()
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda rec: not rec.sudo().skip_constraints_confirm):
            issues = rec.check_overtime_request_constraints()
            if issues:
                raise exceptions.ValidationError(issues)
        return res

    @api.multi
    def check_overtime_request_constraints(self):
        self.ensure_one()
        template = self.env.ref('e_document.overtime_request_template', False)
        if template and self.template_id.id == template.id:
            if not self.overtime_request_type:
                return _('Request type not specified')
            if not self.overtime_compensation:
                return _('Overtime compensation not specified')
            if not self.e_document_time_line_ids:
                return _('Overtime times not specified')
        return str()


EDocument()
