# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_nedirbti_puse_dienos_pirmaja_mokslo_metu_diena_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref(
                'e_document.isakymas_leisti_nedirbti_puse_dienos_pirmaja_mokslo_metu_diena_template'
            ).id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_2': self.date_2,
            'user_id': self.user_id.id,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
