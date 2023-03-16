# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, fields, models, exceptions, _, tools


class AssetAssignResponsible(models.TransientModel):
    _name = 'asset.assign.responsible'

    date = fields.Date(string='Responsible from', required=True, default=fields.Date.today)
    employee_id = fields.Many2one('hr.employee', string='Responsible employee', required=True)

    @api.multi
    def assign(self):
        asset_ids = self._context.get('active_ids', False)
        if not asset_ids:
            raise exceptions.UserError(_('Could not assign.'))
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        if use_sudo and not self.env.user.has_group('base.group_system'):
            for asset in self.env['account.asset.asset'].browse(asset_ids):
                asset.message_post('Assigning responsible employee')
            self = self.sudo()
        for asset_id in asset_ids:
            resp_obj = self.env['account.asset.responsible']
            curr = resp_obj.search([('asset_id', '=', asset_id)], order='date DESC', limit=1)
            if curr:
                curr_date = datetime.strptime(curr.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date <= curr_date:
                    raise exceptions.UserError(_('You must select a newer date.'))
                if curr.employee_id.id == self.employee_id.id:
                    raise exceptions.UserError(_('You try to assign currently responsible employee.'))
            responsible = resp_obj.create({
                'asset_id': asset_id,
                'employee_id': self.employee_id.id,
                'date': self.date,
            })
            if self.employee_id.user_id:
                responsible.invite_sign()
        return


AssetAssignResponsible()
