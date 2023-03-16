# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_nemokamu_atostogu_suteikimo_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_nemokamu_atostogu_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'job_id1': self.job_id2.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'text_3': self.text_1,
            'text_2': self.text_4,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
