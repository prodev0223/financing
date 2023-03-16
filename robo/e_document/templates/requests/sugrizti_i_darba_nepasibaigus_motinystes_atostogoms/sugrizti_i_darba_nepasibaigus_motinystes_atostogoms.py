# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_sugrizti_i_darba_nepasibaigus_motinystes_atostogoms_workflow(self):
        self.ensure_one()
        pass


EDocument()
