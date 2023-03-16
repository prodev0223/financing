# -*- coding: utf-8 -*-
from odoo import models, api, fields, exceptions, tools, _

TEMPLATE = 'e_document.isakymas_del_nepanaudotu_atostogu_anuliavimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    remaining_leaves_label = fields.Char(string='Remaining leaves', compute='_compute_remaining_leaves_label',
                                         store=True)

    @api.depends('employee_id2', 'date_document')
    def _compute_remaining_leaves_label(self):
        for rec in self:
            if rec.template_id == self.env.ref(TEMPLATE, False):
                rec.remaining_leaves_label = rec.employee_id2.with_context(date=rec.date_document). \
                    remaining_leaves_label

    @api.multi
    def isakymas_del_nepanaudotu_atostogu_anuliavimo_workflow(self):
        self.ensure_one()
        holiday_fix = self.env['hr.holidays.fix'].adjust_fix_days(self.employee_id2, self.date_document, -self.float_1)
        self.write({
            'record_model': 'hr.holidays.fix',
            'record_id': holiday_fix.id,
        })

    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self:
            if rec.template_id == self.env.ref(TEMPLATE, False):
                rec._compute_remaining_leaves_label()
                if rec.template_id == self.env.ref(TEMPLATE, False):
                    remaining_leaves = rec.employee_id2.with_context(date=rec.date_document).remaining_leaves
                    if tools.float_compare(rec.float_1, remaining_leaves, precision_digits=2) == 1:
                        raise exceptions.ValidationError(_('Negalima nurašyti daugiau atostogų dienų, '
                                                           'negu jų yra sukaupta.'))

        return res

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        document_to_cancel = self.cancel_id
        if document_to_cancel and document_to_cancel.template_id == self.env.ref(TEMPLATE, False):
            existing_fix = self.env['hr.holidays.fix'].search([
                ('employee_id', '=', document_to_cancel.employee_id2.id),
                ('date', '=', document_to_cancel.date_document),
                ('type', '=', 'add'),
            ])
            if not existing_fix:
                raise exceptions.ValidationError(_('Nerastas fiksuoto atostogų likučio įrašas.'))
            existing_fix = self.env['hr.holidays.fix'].adjust_fix_days(document_to_cancel.employee_id2,
                                                                       document_to_cancel.date_document,
                                                                       document_to_cancel.float_1)
            # Can only unlink fix if the existing accounted for the adjusted days have 0 day adjustment
            can_unlink_fix = existing_fix and \
                tools.float_is_zero(existing_fix.get_calendar_days() + existing_fix.get_work_days(), precision_digits=2)
            if can_unlink_fix:
                existing_fix.unlink()
        else:
            super(EDocument, self).execute_cancel_workflow()


EDocument()
