# -*- coding: utf-8 -*-
from odoo import fields, models, api, exceptions, _


class AccountAssetResponsible(models.Model):
    _name = 'account.asset.responsible'
    _description = 'Registry of materially responsible employees'
    _order = 'date DESC'
    _rec_name = 'asset_id'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Responsible Employee', required=True, ondelete='cascade')
    date = fields.Date(string='Materially responsible from', required=True)
    sign_id = fields.Many2one('e.document', string='eDokumentas', ondelete='set null', readonly=True)
    document_state = fields.Selection(string='Dokumento būsena', related='sign_id.state', readonly=True)

    @api.multi
    def invite_sign(self):
        self.ensure_one()
        if not self.employee_id.user_id:
            raise exceptions.UserError(_('Darbuotojas %s neturi susijusio vartotojo.') % self.employee_id.name)
        # Ensure that user IDs in the list are not doubled
        users = self.sudo().env.user.company_id.vadovas.user_id | self.employee_id.user_id
        action = self.env['e.document'].general_sign_call(
            'ilgalaikis_turtas.asset_responsible_report_template', self, user_ids=users.ids)
        if action and 'res_id' in action and action['res_id']:
            self.sign_id = action['res_id']
        return action

