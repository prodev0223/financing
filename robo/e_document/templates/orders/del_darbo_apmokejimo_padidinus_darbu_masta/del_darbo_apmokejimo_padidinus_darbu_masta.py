# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_darbo_apmokejimo_padidinus_darbu_masta_workflow(self):
        self.ensure_one()
        # no workflow


EDocument()
