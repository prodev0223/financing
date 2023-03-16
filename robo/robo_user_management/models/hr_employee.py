# -*- coding: utf-8 -*-

from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.multi
    def open_user_card(self):
        self.ensure_one()
        if not self.user_id:
            return
        action = self.env.ref('robo_user_management.res_users_front_end_view_action')
        action = action.read()[0]
        action['view_type'] = 'form'
        action['views'] = [(self.env.ref('robo_user_management.res_users_front_end_form_view').id, 'form')]
        action['res_id'] = self.user_id.id
        return action


HrEmployee()
