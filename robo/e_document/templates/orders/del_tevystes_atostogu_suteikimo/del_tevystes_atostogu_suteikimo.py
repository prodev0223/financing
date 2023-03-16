# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _
from .... model import e_document_tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_tevystes_atostogu_suteikimo_workflow(self):
        self.ensure_one()

        skip = self.check_skip_leave_creation()
        if not skip:
            hol_id = self.env['hr.holidays'].create({
                'name': 'Tėvystės atostogos',
                'data': self.date_document,
                'employee_id': self.employee_id2.id,
                'holiday_status_id': self.env.ref('hr_holidays.holiday_status_TA').id,
                'date_from': self.calc_date_from(self.date_from),
                'date_to': self.calc_date_to(self.date_to),
                'type': 'remove',
                'numeris': self.document_number,
                'child_birthdate': self.date_3,
                'child_person_code': self.text_4 or '',
            })
            hol_id.action_approve()
            self.inform_about_creation(hol_id)
            self.write({
                'record_model': 'hr.holidays',
                'record_id': hol_id.id,
            })

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self:
            if rec.template_id.id == self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id:
                if rec.text_4 and not e_document_tools.assert_correct_identification_id(rec.text_4):
                    raise exceptions.ValidationError(_('Neteisingas vaiko asmens kodas'))
        return res


EDocument()
