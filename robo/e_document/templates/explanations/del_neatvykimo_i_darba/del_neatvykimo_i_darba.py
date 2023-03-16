# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def pasiaiskinimas_del_neatvykimo_i_darba_workflow(self):
        self.ensure_one()
        pass


EDocument()
