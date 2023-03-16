# -*- coding: utf-8 -*-
from odoo import models, api, _


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    @api.multi
    def button_open_ebay_settings(self):
        """
        Open eBay settings window. If settings object is not yet created, create one.
        :return: JS action (dict)
        """
        # Always one record
        ebay_config = self.env['ebay.configuration'].search([], limit=1)
        action = {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'ebay.configuration',
            'res_id': ebay_config.id,
            'view_id': self.env.ref('ebay.ebay_configuration_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }
        return action
