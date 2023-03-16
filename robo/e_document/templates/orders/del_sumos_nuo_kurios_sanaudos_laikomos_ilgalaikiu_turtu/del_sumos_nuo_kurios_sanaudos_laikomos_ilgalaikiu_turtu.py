# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_sumos_nuo_kurios_sanaudos_laikomos_ilgalaikiu_turtu_workflow(self):
        self.ensure_one()
        self.company_id.write({'longterm_assets_min_val': self.float_1,
                               'longterm_non_material_assets_min_val': self.float_2})


EDocument()
