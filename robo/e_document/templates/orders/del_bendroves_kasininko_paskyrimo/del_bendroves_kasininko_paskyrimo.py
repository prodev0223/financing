# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_bendroves_kasininko_paskyrimo_workflow(self):
        self.ensure_one()
        user = self.employee_id2.user_id
        user.write({'groups_id': [(4, self.env.ref('robo_basic.group_robo_cash_manager').id)]})


EDocument()
