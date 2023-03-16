# -*- coding: utf-8 -*-
from odoo import models, api, _, exceptions


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_pavardes_pakeitimo_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_pavardes_keitimo_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'user_id': self.user_id.id,
            'text_1': self.text_1,
            'text_2': self.text_2,
            'date_1': self.date_1,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.prasymas_del_pavardes_pakeitimo_template',
                                False)
        for rec in self.filtered(lambda r: r.sudo().template_id == template and not r.sudo().skip_constraints_confirm):
            if not rec.text_1 and not rec.document_1:
                raise exceptions.UserError(_('Turi būti įkeltas santuokos liudijimo dokumentas arba įrašytas jo numeris.'))

EDocument()
