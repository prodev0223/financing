# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_darbuotojo_skyrimo_dirbti_poilsio_diena_workflow(self):
        self.ensure_one()
        # No workflow


EDocument()
