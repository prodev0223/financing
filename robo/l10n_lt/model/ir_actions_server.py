# -*- coding: utf-8 -*-
from odoo import models, _, api


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    @api.multi
    def create_action(self):
        """ Create a contextual action for each server action. """
        for action in self:
            if not self.env['ir.values'].search_count([('value', '=', 'ir.actions.server,%s' % action.id)]):
                ir_values = self.env['ir.values'].sudo().create({
                    'name': _('Run %s') % action.name,
                    'model': action.model_id.model,
                    'key2': 'client_action_multi',
                    'value': "ir.actions.server,%s" % action.id,
                })
                action.write({'menu_ir_values_id': ir_values.id})
        return True
