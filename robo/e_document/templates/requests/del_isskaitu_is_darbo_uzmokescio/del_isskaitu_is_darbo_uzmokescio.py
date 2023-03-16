# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_isskaitu_is_darbo_uzmokescio_workflow(self):
        self.ensure_one()
        user_id = self.user_id.id
        contract = self.env['hr.contract'].search([('employee_id.user_id', '=', user_id),
                                                   ('date_start', '>=', self.date_2), '|', ('date_end', '=', False),
                                                   ('date_end', '>=', self.date_to)])
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_isskaitu_is_darbo_uzmokescio_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_5': self.date_2,
            'date_2': self.date_document,
            'float_1': self.float_1,
            'user_id': self.user_id.id,
            'text_3': self.text_3,
            'text_8': self.text_7,
            'text_3': self.text_4,
            'text_4': self.text_1,
            'text_5': '1 mėnesis',
            'date_3': contract.date_start,
            'contract_id': contract.id,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})


EDocument()
