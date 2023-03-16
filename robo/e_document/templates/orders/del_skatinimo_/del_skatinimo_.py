# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_skatinimo__workflow(self):
        self.ensure_one()
        # No workflow


EDocument()
