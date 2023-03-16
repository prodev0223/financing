# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_naudojamo_ligos_koeficiento_workflow(self):
        self.ensure_one()
        self.env['payroll.parameter.history'].create({
            'date_from': self.date_from,
            'field_name': 'ligos_koeficientas',
            'value': self.float_1,
            'company_id': self.company_id.id
        })


EDocument()
