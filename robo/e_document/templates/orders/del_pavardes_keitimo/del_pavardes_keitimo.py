# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_pavardes_keitimo_workflow(self):
        self.ensure_one()
        self.employee_id2.write({
            'name': ' '.join(self.employee_id2.name.split(' ')[:-1]) + ' ' + self.text_2,
        })


EDocument()
