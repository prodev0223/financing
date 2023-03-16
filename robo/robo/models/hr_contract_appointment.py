# -*- coding: utf-8 -*-


from odoo import api, fields, models


class HrContractAppointment(models.Model):
    _inherit = 'hr.contract.appointment'

    neto_compute = fields.Float(compute='get_neto')
    hide_neto = fields.Boolean(compute='_compute_hide_neto')

    @api.one
    @api.depends('neto_monthly', 'struct_id')
    def get_neto(self):
        if self.struct_id.code == 'MEN':
            self.neto_compute = self.neto_monthly

    @api.multi
    @api.depends('struct_id')
    def _compute_hide_neto(self):
        for rec in self:
            rec.hide_neto = True if rec.struct_id.code == 'VAL' else False
