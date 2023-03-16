# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, api, exceptions, _, tools
from .... model import e_document_tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_vaiko_prieziuros_atostogu_suteikimo_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_1': self.date_1,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'int_2': self.int_1,
            'date_3': self.date_3,
            'text_4': self.text_4,

        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    @api.constrains('text_4')
    def constraints_child_person_code(self):
        template_ids = [self.env.ref('e_document.prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template').id,
                        self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template').id]
        for rec in self:
            if rec.template_id.id in template_ids and rec.text_4 \
                    and not e_document_tools.assert_correct_identification_id(rec.text_4):
                        raise exceptions.ValidationError(_('Neteisingas vaiko asmens kodas!'))


EDocument()
