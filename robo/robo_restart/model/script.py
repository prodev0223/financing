# -*- coding: utf-8 -*-
from odoo import models, api


class Script(models.Model):
    _inherit = 'script'

    @api.model
    def _reset_running_status(self):
        """ Reset running field to False """
        self.search([('running', '=', True)]).write({'running': False})


Script()
