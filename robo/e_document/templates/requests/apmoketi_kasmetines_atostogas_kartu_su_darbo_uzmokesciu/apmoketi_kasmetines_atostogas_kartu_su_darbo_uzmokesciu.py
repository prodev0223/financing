# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_apmoketi_kasmetines_atostogas_kartu_su_darbo_uzmokesciu_workflow(self):
        self.ensure_one()
        pass


EDocument()
