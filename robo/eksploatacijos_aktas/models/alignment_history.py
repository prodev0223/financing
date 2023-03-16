# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AlignmentHistory(models.Model):
    _name = 'alignment.history'
    _description = 'Alignment History'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True, required=True)
    aligned = fields.Boolean(string='Signed', compute='_compute_aligned', store=True)
    comment = fields.Text(string='Comment', required=False, readonly=True)
    invited = fields.Boolean(string='Invited', default=False)

    eks_aktas_id = fields.Many2one('eksploatacijos.aktas', string='Operation Act', required=False)

    @api.depends('eks_aktas_id.sign_id.user_ids.state')
    def _compute_aligned(self):
        for rec in self:
            signed_user = rec.sudo().mapped('eks_aktas_id.sign_id.user_ids').filtered(lambda u: u.user_id == rec.employee_id.user_id)
            if not signed_user:
                continue
            rec.aligned = signed_user[0].state == 'signed'



AlignmentHistory()
