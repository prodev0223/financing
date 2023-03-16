# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_perkelti_kasmetiniu_atostogu_dali_workflow(self):
        self.ensure_one()
        pass


EDocument()
