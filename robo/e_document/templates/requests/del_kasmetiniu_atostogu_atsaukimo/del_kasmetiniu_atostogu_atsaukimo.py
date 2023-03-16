# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _
from datetime import datetime


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_kasmetiniu_atostogu_atsaukimo_workflow(self):
        self.ensure_one()
        if self.cancel_id:
            self.cancel_id.sudo().cancel_order()
        else:
            raise exceptions.UserError(_('Nėra susijusio dokumento, kurį būtų galima atšaukti.'))


EDocument()
