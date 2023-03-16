# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_suteikti_mokymosi_atostogas_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_mokymosi_atostogu_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_1': self.date_1,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'text_3': self.text_2,
            'text_2': self.text_4,

        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
