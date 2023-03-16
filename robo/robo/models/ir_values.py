# -*- coding: utf-8 -*-


from odoo import api, models


class IrValues(models.Model):
    _inherit = 'ir.values'

    @api.model
    def get_actions(self, action_slot, model, res_id=False):
        results = super(IrValues, self).get_actions(action_slot, model, res_id)
        if not self.env.user.is_back_user():
            results = [x for x in results if x[2] and x[2].get('robo_front')]
        return results
