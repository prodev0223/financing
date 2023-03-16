# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_mamadienio_tevadienio_suteikimo_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_mamadienio_/_tevadienio_suteikimo_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'num_extra_days': self.num_extra_days,
            'num_children': self.num_children,
            'date_3': self.date_3,
            'date_4': self.date_4,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
