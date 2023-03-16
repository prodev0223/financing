# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_susitarimo_nutraukimo_workflow(self):
        self.ensure_one()
        self.execute_cancel_workflow()


EDocument()
