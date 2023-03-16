# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    politika_atostogu_suteikimas = fields.Selection(
        [('ceo', 'Tvirtina vadovas'), ('department', 'Padalinio vadovas')], string='Atostogų tvirtinimas',
        compute='_compute_politika_atostogu_suteikimas')
    department_delegate_ids = fields.One2many('e.document.department.delegate', 'department_id', string='Įgaliotiniai')

    @api.one
    @api.depends('company_id.politika_atostogu_suteikimas')
    def _compute_politika_atostogu_suteikimas(self):
        self.politika_atostogu_suteikimas = self.env.user.sudo().company_id.politika_atostogu_suteikimas


HrDepartment()
