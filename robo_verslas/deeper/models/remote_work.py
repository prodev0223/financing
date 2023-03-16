# -*- coding: utf-8 -*-

from odoo import models, api, fields, _, exceptions, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def create_remote_work_appointments(self, working_remotely=True):
        pass
