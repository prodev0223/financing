# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_leisti_neatvykti_i_darba_workflow(self):
        self.ensure_one()
        template_id = self.env.ref('e_document.isakymas_del_neatvykimo_i_darba_darbdaviui_leidus_template').id
        generated_id = self.env['e.document'].create({
            'template_id': template_id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_1': self.date_1,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,

        })
        generated_id._onchange_employee_id2_update_float_1_to_match_vdu()
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
