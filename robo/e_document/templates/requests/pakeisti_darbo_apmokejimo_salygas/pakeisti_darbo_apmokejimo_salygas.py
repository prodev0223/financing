# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_pakeisti_darbo_apmokejimo_salygas_workflow(self):
        self.ensure_one()
        pass


EDocument()
