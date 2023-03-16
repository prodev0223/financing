# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_papildomos_lengvatos_auginant_vaikus_workflow(self):
        self.ensure_one()
        pass


EDocument()
