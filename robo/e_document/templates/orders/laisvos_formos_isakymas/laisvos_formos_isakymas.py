# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def laisvos_formos_isakymas_workflow(self):
        self.ensure_one()
        # No workflow


EDocument()
