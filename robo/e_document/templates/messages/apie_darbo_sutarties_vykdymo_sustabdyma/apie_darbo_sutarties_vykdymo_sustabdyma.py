# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def pranesimas_apie_darbo_sutarties_vykdymo_sustabdyma_workflow(self):
        self.ensure_one()
        pass


EDocument()
