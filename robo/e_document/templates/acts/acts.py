# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import models, api, fields, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def cancel_act(self):
        self.ensure_one()
        self.execute_cancel_workflow()
        self.sudo().write({'state': 'cancel', 'cancel_uid': self.env.uid})


EDocument()
