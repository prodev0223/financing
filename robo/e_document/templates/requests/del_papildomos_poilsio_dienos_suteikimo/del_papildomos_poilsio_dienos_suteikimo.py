# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_papildomos_poilsio_dienos_suteikimo_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_papildomos_poilsio_dienos_suteikimo_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
