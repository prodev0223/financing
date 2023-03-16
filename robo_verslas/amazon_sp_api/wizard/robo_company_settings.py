# -*- coding: utf-8 -*-
from odoo import models, api, _


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    @api.multi
    def button_open_amazon_sp_api_settings(self):
        """
        Open Amazon SP-API settings window. If settings object is not yet created, create one.
        :return: JS action (dict)
        """
        # Always one record
        sp_config = self.env['amazon.sp.configuration'].search([], limit=1)
        action = {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'amazon.sp.configuration',
            'res_id': sp_config.id,
            'view_id': self.env.ref('amazon_sp_api.amazon_sp_configuration_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }
        return action
