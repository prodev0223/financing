# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.model
    def _reset_running_status(self):
        """ Reset running field to False """
        self.search([('running', '=', True)]).write({'running': False})


EDocument()
