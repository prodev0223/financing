# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_isskaitu_is_darbo_uzmokescio_workflow(self):
        self.ensure_one()
        # No workflow


EDocument()
