# -*- coding: utf-8 -*-
from odoo import models, api


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    @api.multi
    def btn_open_r_keeper_settings(self):
        """
        Initiates rKeeper configuration if record does not already exist
        and returns the action to open the form view.
        :return: JS Action (dict)
        """
        configuration = self.env['r.keeper.configuration'].initiate_configuration()
        action = {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'r.keeper.configuration',
            'res_id': configuration.id,
            'view_id': self.env.ref('r_keeper.form_r_keeper_configuration').id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }
        return action
